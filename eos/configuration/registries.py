import inspect
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

# Apply the sila2/upb compat shim before any user plugin module is loaded, so
# `from sila2.client import SilaClient` at device.py top-level works alongside
# Ray's upb protobuf. No-op when sila2 isn't installed.
from eos.integrations.sila import _upb_compat  # noqa: F401

from eos.configuration.constants import CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME, CAMPAIGN_OPTIMIZER_FILE_NAME
from eos.configuration.entities.device_spec_def import DeviceSpecDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.configuration.exceptions import (
    EosCampaignOptimizerPluginError,
    EosDevicePluginError,
    EosTaskPluginError,
)
from eos.configuration.packages import ENTITY_INFO, EntityType, Package, PackageManager
from eos.devices.base_device import BaseDevice, build_device_spec
from eos.logging.batch_error_logger import batch_error, raise_batched_errors
from eos.logging.logger import log
from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.tasks.task_definition import TaskDefinition
from eos.utils.singleton import Singleton

T = TypeVar("T")  # Plugin type
S = TypeVar("S", bound=BaseModel)  # Spec type


# =============================================================================
# Specification Registry
# =============================================================================


class SpecRegistry(Generic[S]):
    """Stores specifications by type, along with the package directory each one was loaded from."""

    def __init__(self, specifications: dict[str, S], dirs_to_types: dict[Path, str]):
        self._specifications = specifications.copy()
        self._dirs_to_types = dirs_to_types.copy()

    def get_all_specs(self) -> dict[str, S]:
        return self._specifications

    def get_spec_by_type(self, spec_type: str) -> S | None:
        return self._specifications.get(spec_type)

    def get_spec_by_config(self, config: Any) -> S | None:
        return self._specifications.get(config.type)

    def resolve_type(self, name: str) -> str | None:
        """Resolve a name to a spec type. Accepts a type name or a directory name."""
        if name in self._specifications:
            return name
        for dir_key, type_name in self._dirs_to_types.items():
            if Path(dir_key).name == name:
                return type_name
        return None

    def get_dir_by_type(self, spec_type: str) -> Path | None:
        """Return the directory key (package name + relative entity dir) for the given type."""
        for dir_key, type_name in self._dirs_to_types.items():
            if type_name == spec_type:
                return Path(dir_key)
        return None

    def spec_exists_by_config(self, config: Any) -> bool:
        return config.type in self._specifications

    def spec_exists_by_type(self, spec_type: str) -> bool:
        return spec_type in self._specifications

    def set_spec(self, spec_type: str, spec: S, dir_key: Path) -> None:
        """Add or replace a single specification, dropping any type previously loaded from the same directory."""
        previous_type = self._dirs_to_types.get(dir_key)
        if previous_type is not None and previous_type != spec_type:
            self._specifications.pop(previous_type, None)
        self._specifications[spec_type] = spec
        self._dirs_to_types[dir_key] = spec_type

    def update_specs(self, specifications: dict[str, S], dirs_to_types: dict[Path, str]) -> None:
        self._specifications = specifications.copy()
        self._dirs_to_types = dirs_to_types.copy()


class TaskSpecRegistry(SpecRegistry[TaskSpecDef], metaclass=Singleton):
    """Task specification registry singleton."""


class DeviceSpecRegistry(SpecRegistry[DeviceSpecDef], metaclass=Singleton):
    """Device specification registry singleton."""


# =============================================================================
# Plugin Registry
# =============================================================================


@dataclass(frozen=True)
class PluginRegistryConfig(Generic[T, S]):
    entity_type: EntityType
    exception_class: type[Exception]
    # Returns (type, plugin, spec) for every plugin defined in a module
    extract: Callable[[ModuleType], list[tuple[str, T, S]]]


class PluginRegistry(Generic[T, S]):
    """Imports task or device modules from packages and registers their implementations and specs."""

    def __init__(self, package_manager: PackageManager, spec_registry: SpecRegistry[S], config: PluginRegistryConfig):
        self._package_manager = package_manager
        self._spec_registry = spec_registry
        self._config = config
        self.plugin_types: dict[str, T] = {}

    def load_all(self) -> None:
        """Import every plugin of every package and replace the registered plugins and specs."""
        plugins: dict[str, T] = {}
        specs: dict[str, S] = {}
        dirs_to_types: dict[Path, str] = {}

        for package in self._package_manager.get_all_packages():
            for relative_dir in self._package_manager.find_entity_dirs(package, self._config.entity_type):
                loaded = self._load(package, relative_dir)
                if loaded is None:
                    continue
                type_name, plugin, spec = loaded
                if type_name in specs:
                    batch_error(
                        f"Duplicate {self._entity_name} type '{type_name}' in '{package.name}/{relative_dir}'.",
                        self._config.exception_class,
                    )
                    continue
                plugins[type_name] = plugin
                specs[type_name] = spec
                dirs_to_types[Path(package.name) / relative_dir] = type_name

        raise_batched_errors(root_exception_type=self._config.exception_class)
        self.plugin_types = plugins
        self._spec_registry.update_specs(specs, dirs_to_types)

    def get_plugin_class_type(self, type_name: str) -> T:
        if type_name not in self.plugin_types:
            raise self._config.exception_class(f"No {self._entity_name} implementation found for type '{type_name}'.")
        return self.plugin_types[type_name]

    def reload_plugin(self, type_name: str) -> str:
        """Re-import a plugin and its package from disk, refreshing its implementation and spec. Returns its type."""
        dir_key = self._spec_registry.get_dir_by_type(type_name)
        if dir_key is None:
            raise self._config.exception_class(f"{self._entity_name.capitalize()} '{type_name}' not found.")

        package_name, *relative_parts = dir_key.parts
        package = self._package_manager.get_package(package_name)
        if package is None:
            raise self._config.exception_class(f"Package '{package_name}' of '{type_name}' is not loaded.")

        self._package_manager.purge_modules(package)
        loaded = self._load(package, Path(*relative_parts))
        raise_batched_errors(root_exception_type=self._config.exception_class)

        new_type, plugin, spec = loaded
        if new_type != type_name:
            if self._spec_registry.spec_exists_by_type(new_type):
                raise self._config.exception_class(
                    f"Cannot rename {self._entity_name} '{type_name}' to '{new_type}', which already exists."
                )
            self.plugin_types.pop(type_name, None)
        self.plugin_types[new_type] = plugin
        self._spec_registry.set_spec(new_type, spec, dir_key)
        log.debug(f"Reloaded {self._entity_name} '{new_type}'")
        return new_type

    @property
    def _entity_name(self) -> str:
        return self._config.entity_type.name.lower()

    def _load(self, package: Package, relative_dir: Path) -> tuple[str, T, S] | None:
        """Import one plugin module, batching an error unless it defines exactly one plugin."""
        info = ENTITY_INFO[self._config.entity_type]
        module_path = Path(info.dir_name) / relative_dir / info.file_name
        location = f"{package.name}/{module_path}"

        try:
            module = self._package_manager.import_module(package, module_path)
            found = self._config.extract(module)
        except Exception as e:
            batch_error(f"Failed to load '{location}': {e}", self._config.exception_class)
            return None

        if len(found) != 1:
            batch_error(
                f"'{location}' must define exactly one {self._entity_name}, found {len(found)}.",
                self._config.exception_class,
            )
            return None

        log.debug(f"Loaded {self._entity_name} '{found[0][0]}' from {location}")
        return found[0]


def _extract_tasks(module: ModuleType) -> list[tuple[str, TaskDefinition, TaskSpecDef]]:
    return [
        (obj.type, obj, obj.spec)
        for obj in vars(module).values()
        if isinstance(obj, TaskDefinition) and obj.fn.__module__ == module.__name__
    ]


def _extract_devices(module: ModuleType) -> list[tuple[str, type[BaseDevice], DeviceSpecDef]]:
    return [
        (obj.device_type, obj, build_device_spec(obj))
        for obj in vars(module).values()
        if inspect.isclass(obj)
        and issubclass(obj, BaseDevice)
        and obj.__module__ == module.__name__
        and obj.device_type is not None
    ]


def create_task_plugin_registry(
    package_manager: PackageManager, task_specs: TaskSpecRegistry
) -> PluginRegistry[TaskDefinition, TaskSpecDef]:
    config = PluginRegistryConfig(EntityType.TASK, EosTaskPluginError, _extract_tasks)
    return PluginRegistry(package_manager, task_specs, config)


def create_device_plugin_registry(
    package_manager: PackageManager, device_specs: DeviceSpecRegistry
) -> PluginRegistry[type[BaseDevice], DeviceSpecDef]:
    config = PluginRegistryConfig(EntityType.DEVICE, EosDevicePluginError, _extract_devices)
    return PluginRegistry(package_manager, device_specs, config)


# =============================================================================
# Campaign Optimizer Plugin Registry
# =============================================================================

CampaignOptimizerCreationFunction = Callable[[], tuple[dict[str, Any], type[AbstractSequentialOptimizer]]]


class CampaignOptimizerPluginRegistry:
    """Lazily imports campaign optimizers from protocol directories."""

    def __init__(self, package_manager: PackageManager):
        self._package_manager = package_manager
        self.plugin_types: dict[str, CampaignOptimizerCreationFunction] = {}

    def get_campaign_optimizer_creation_parameters(
        self, protocol_type: str
    ) -> tuple[dict[str, Any], type[AbstractSequentialOptimizer]] | None:
        """
        Get the constructor arguments and the optimizer type so it can be constructed later.
        Lazy-loads the optimizer plugin on first access.

        :param protocol_type: The type of the protocol.
        :return: A tuple containing the constructor arguments and the optimizer type, or None if not found.
        """
        if protocol_type not in self.plugin_types:
            self.load_campaign_optimizer(protocol_type)
        optimizer_function = self.plugin_types.get(protocol_type)
        return optimizer_function() if optimizer_function else None

    def load_campaign_optimizer(self, protocol_type: str) -> None:
        """Load the optimizer of a protocol. Logs a warning and returns if the protocol has none."""
        package = self._package_manager.find_package_for_entity(protocol_type, EntityType.PROTOCOL)
        if not package:
            log.warning(f"No package found for protocol '{protocol_type}'.")
            return

        protocol_dir = self._package_manager.get_entity_dir(protocol_type, EntityType.PROTOCOL)
        optimizer_file = protocol_dir / CAMPAIGN_OPTIMIZER_FILE_NAME
        if not optimizer_file.exists():
            log.warning(f"No campaign optimizer found for protocol '{protocol_type}' in package '{package.name}'.")
            return

        try:
            relative_path = optimizer_file.relative_to(package.path)
            module = self._package_manager.import_module(package, relative_path, fresh=True)
        except Exception as e:
            raise EosCampaignOptimizerPluginError(
                f"Failed to load campaign optimizer of protocol '{protocol_type}': {e}"
            ) from e

        optimizer_creator = getattr(module, CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME, None)
        if optimizer_creator is None:
            log.warning(
                f"Optimizer configuration function '{CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME}' not found in the "
                f"campaign optimizer of protocol '{protocol_type}' in package '{package.name}'."
            )
            return

        self.plugin_types[protocol_type] = optimizer_creator
        log.info(f"Loaded campaign optimizer for protocol '{protocol_type}' from package '{package.name}'.")

    def unload_campaign_optimizer(self, protocol_type: str) -> None:
        if self.plugin_types.pop(protocol_type, None) is not None:
            log.info(f"Unloaded campaign optimizer for protocol '{protocol_type}'.")

    def reload_plugin(self, protocol_type: str) -> None:
        self.unload_campaign_optimizer(protocol_type)
        self.load_campaign_optimizer(protocol_type)
        log.info(f"Reloaded campaign optimizer for protocol '{protocol_type}'.")

    def reload_all_plugins(self) -> None:
        for protocol_type in list(self.plugin_types):
            self.reload_plugin(protocol_type)
        log.info("Reloaded all campaign optimizers.")
