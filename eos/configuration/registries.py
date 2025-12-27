import importlib.util
import inspect
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Generic, TypeVar

from eos.configuration.constants import (
    CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME,
    CAMPAIGN_OPTIMIZER_FILE_NAME,
    DEVICE_CONFIG_FILE_NAME,
    DEVICE_IMPLEMENTATION_FILE_NAME,
    TASK_CONFIG_FILE_NAME,
    TASK_IMPLEMENTATION_FILE_NAME,
)
from eos.configuration.exceptions import (
    EosCampaignOptimizerPluginError,
    EosDevicePluginError,
    EosTaskPluginError,
)
from eos.configuration.packages import EntityType, PackageManager
from eos.logging.batch_error_logger import batch_error, raise_batched_errors
from eos.logging.logger import log
from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.utils.singleton import Singleton

# Type variables
T = TypeVar("T")  # Specification or plugin class type
C = TypeVar("C")  # Configuration type
S = TypeVar("S")  # Spec registry type


# =============================================================================
# Specification Registry
# =============================================================================


class SpecRegistry(Generic[T, C]):
    """
    A generic registry for storing and retrieving specifications.
    """

    def __init__(
        self,
        specifications: dict[str, T],
        dirs_to_types: dict[str, str],
    ):
        self._specifications = specifications.copy()
        self._dirs_to_types = dirs_to_types.copy()

    def get_all_specs(self) -> dict[str, T]:
        return self._specifications

    def get_spec_by_type(self, spec_type: str) -> T | None:
        return self._specifications.get(spec_type)

    def get_spec_by_config(self, config: C) -> T | None:
        return self._specifications.get(config.type)

    def get_spec_by_dir(self, dir_path: str) -> str:
        return self._dirs_to_types.get(dir_path)

    def get_dir_by_type(self, spec_type: str) -> Path | None:
        """
        Return the directory key (including package prefix) for the given type,
        if present in this registry. Keys are stored as Path-like objects.
        """
        for dir_key, type_name in self._dirs_to_types.items():
            if type_name == spec_type:
                # dir_key may be a Path or string; normalize to Path
                return Path(dir_key)
        return None

    def spec_exists_by_config(self, config: C) -> bool:
        return config.type in self._specifications

    def spec_exists_by_type(self, spec_type: str) -> bool:
        return spec_type in self._specifications

    def update_specs(self, specifications: dict[str, T], dirs_to_types: dict[str, str]) -> None:
        """Public method for refreshing specs."""
        self._specifications = specifications.copy()
        self._dirs_to_types = dirs_to_types.copy()


# =============================================================================
# Spec Registry Subclasses
# =============================================================================


class TaskSpecRegistry(SpecRegistry, metaclass=Singleton):
    """Task specification registry - singleton wrapper for SpecRegistry."""


class DeviceSpecRegistry(SpecRegistry, metaclass=Singleton):
    """Device specification registry - singleton wrapper for SpecRegistry."""


# =============================================================================
# Spec Registry Factory Functions
# =============================================================================


def create_task_spec_registry(
    task_specs: dict[str, Any],
    dirs_to_types: dict[str, str],
) -> TaskSpecRegistry:
    """Create a task specification registry with output_resources defaulting."""
    # Apply the _update_output_resources logic
    for spec in task_specs.values():
        if not spec.output_resources:
            spec.output_resources = spec.input_resources.copy()
    return TaskSpecRegistry(task_specs, dirs_to_types)


def create_device_spec_registry(
    device_specs: dict[str, Any],
    dirs_to_types: dict[str, str],
) -> DeviceSpecRegistry:
    """Create a device specification registry."""
    return DeviceSpecRegistry(device_specs, dirs_to_types)


# =============================================================================
# Plugin Registry
# =============================================================================


@dataclass(frozen=True)
class PluginRegistryConfig(Generic[T, S]):
    spec_registry: S
    base_class: type[T] | None
    config_file_name: str | None
    implementation_file_name: str
    exception_class: type[Exception]
    entity_type: EntityType


class PluginRegistry(Generic[T, S]):
    """Registry for discovering, loading, and reloading plugin implementations."""

    def __init__(
        self,
        package_manager: PackageManager,
        config: PluginRegistryConfig[T, S],
        initialize: bool = True,
    ):
        self._package_manager = package_manager
        self._config = config
        self.plugin_types: dict[str, type[T]] = {}
        self.plugin_modules: dict[str, str] = {}
        # Stores (package_name, relative_dir, implementation_path) for each type
        self._plugin_meta: dict[str, tuple[str, Path, Path]] = {}

        if initialize:
            self._initialize_registry()

    def get_plugin_class_type(self, type_name: str) -> type[T]:
        # Return if already loaded
        if type_name in self.plugin_types:
            return self.plugin_types[type_name]

        # Attempt lazy initialization for this specific type if supported
        lazy_init_error = None
        try:
            # Only attempt targeted initialization when we have the machinery
            # to resolve entities (i.e., for task/device registries).
            if self._config.spec_registry is not None:
                self.initialize_for_types({type_name})
        except Exception as e:
            # Capture the error for detailed reporting
            lazy_init_error = e

        # Return if loaded by lazy init; otherwise, raise a detailed error
        if type_name in self.plugin_types:
            return self.plugin_types[type_name]

        # Build detailed error message
        if lazy_init_error:
            raise self._config.exception_class(
                f"Failed to load plugin implementation for '{type_name}': {lazy_init_error}"
            ) from lazy_init_error
        raise self._config.exception_class(
            f"Plugin implementation for '{type_name}' not found. Ensure the plugin exists and is properly registered."
        )

    def reload_plugin(self, type_name: str) -> None:
        """Reload a specific plugin by type name, pulling fresh code from disk."""
        meta = self._plugin_meta.get(type_name)
        if meta is None:
            raise self._config.exception_class(f"Plugin '{type_name}' not found.")

        package_name, relative_dir, impl_path = meta
        module_name = self._make_module_name(package_name, relative_dir.name)

        if module_name in sys.modules:
            del sys.modules[module_name]

        self._load_single_plugin(package_name, relative_dir, impl_path)
        log.debug(f"Reloaded plugin '{type_name}'")

    def reload_all_plugins(self) -> None:
        """Clear and rebuild the entire registry from disk."""
        self.plugin_types.clear()
        self.plugin_modules.clear()
        self._plugin_meta.clear()
        self._initialize_registry()
        log.debug("Reloaded all plugins")

    def _initialize_registry(self) -> None:
        """Walk every package and load its plugins."""
        for pkg in self._package_manager.get_all_packages():
            self._load_package_plugins(pkg)
        raise_batched_errors(root_exception_type=self._config.exception_class)

    def _load_package_plugins(self, package) -> None:
        """Load all plugins under one package's entity directory."""
        entity_dir = package.get_entity_dir(self._config.entity_type)
        if not entity_dir.is_dir() or not self._config.config_file_name:
            return

        for root, _, files in os.walk(entity_dir):
            if self._config.config_file_name not in files:
                continue

            relative = Path(root).relative_to(entity_dir)
            impl_file = Path(root) / self._config.implementation_file_name
            self._load_single_plugin(package.name, relative, impl_file)

    def _load_single_plugin(self, package_name: str, relative_dir: Path, impl_file: Path) -> None:
        """Load/register one plugin file, reporting errors to the batch logger."""
        if not impl_file.exists():
            batch_error(
                f"Implementation file '{impl_file}' for package '{package_name}' not found.",
                self._config.exception_class,
            )
            return

        module_name = self._make_module_name(package_name, relative_dir.name)
        module = self._import_module_from_file(module_name, impl_file)
        if not module:
            return

        cls = self._extract_implementation_class(module)
        if not cls:
            return

        self._register_plugin(cls, package_name, relative_dir, impl_file)

    def _make_module_name(self, package_name: str, dir_name: str) -> str:
        """Create a unique module name for importlib from package + dir."""
        return f"{package_name}.{dir_name}"

    def _import_module_from_file(self, module_name: str, path: Path) -> object | None:
        """Load a module via importlib.util from an arbitrary file path."""
        try:
            spec = importlib_util.spec_from_file_location(module_name, str(path))
            module = importlib_util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore
            return module
        except Exception as e:
            batch_error(
                f"Failed to import '{module_name}' from '{path}': {e}",
                self._config.exception_class,
            )
            return None

    def _extract_implementation_class(self, module: object) -> type[T] | None:
        """Find exactly one subclass of base_class in the given module."""
        candidates = [
            obj
            for obj in vars(module).values()
            if inspect.isclass(obj) and issubclass(obj, self._config.base_class) and obj is not self._config.base_class
        ]
        if not candidates:
            batch_error(
                f"No subclass of '{self._config.base_class.__name__}' found in module {module}.",
                self._config.exception_class,
            )
            return None
        if len(candidates) > 1:
            names = ", ".join(c.__name__ for c in candidates)
            batch_error(
                f"Multiple subclasses in module {module}: {names}. Only one allowed.",
                self._config.exception_class,
            )
            return None
        return candidates[0]

    def _register_plugin(
        self,
        cls: type[T],
        package_name: str,
        relative_dir: Path,
        impl_file: Path,
    ) -> None:
        """Record a freshly loaded plugin in our lookup tables."""
        type_name = self._config.spec_registry.get_spec_by_dir(Path(package_name) / relative_dir)
        self.plugin_types[type_name] = cls
        self.plugin_modules[type_name] = str(impl_file)
        self._plugin_meta[type_name] = (package_name, relative_dir, impl_file)
        log.debug(f"Loaded plugin '{type_name}' ({cls.__name__}) from {impl_file}")

    def initialize_for_types(self, types: set[str]) -> None:
        """
        Load (or reload) only the given set of plugin types.
        Any errors are batched and raised together.
        """
        errors: list[tuple[str, type[Exception]]] = []

        for type_name in types:
            try:
                # Resolve exclusively via spec registry (type -> <package>/<relative_dir>)
                if self._config.spec_registry is None:
                    errors.append((f"Spec registry not configured for '{type_name}'", self._config.exception_class))
                    continue

                resolved_dir = self._config.spec_registry.get_dir_by_type(type_name)
                if resolved_dir is None:
                    errors.append((f"No specification found for type '{type_name}'", self._config.exception_class))
                    continue

                parts = resolved_dir.parts
                if not parts:
                    errors.append((f"Invalid directory mapping for '{type_name}'", self._config.exception_class))
                    continue

                package_name = parts[0]
                relative = Path(*parts[1:]) if len(parts) > 1 else Path()
                pkg = self._package_manager.get_package(package_name)
                if not pkg:
                    errors.append(
                        (f"Package '{package_name}' not found for '{type_name}'", self._config.exception_class)
                    )
                    continue

                entity_dir = pkg.get_entity_dir(self._config.entity_type) / relative
                impl_file = entity_dir / self._config.implementation_file_name
                if not impl_file.exists():
                    errors.append(
                        (
                            f"Implementation file for '{type_name}' not found at '{impl_file}'",
                            self._config.exception_class,
                        )
                    )
                    continue

                self._load_single_plugin(pkg.name, relative, impl_file)

            except Exception as e:
                errors.append((f"Error loading plugin '{type_name}': {e}", self._config.exception_class))

        # Raise any batched errors from _load_single_plugin calls
        raise_batched_errors(root_exception_type=self._config.exception_class)

        if errors:
            combined = "\n".join(f"{msg} ({exc.__name__})" for msg, exc in errors)
            raise self._config.exception_class(combined)


# =============================================================================
# Plugin Registry Factory Functions
# =============================================================================


def create_task_plugin_registry(
    package_manager: PackageManager,
    task_specs: SpecRegistry,
) -> PluginRegistry:
    """Create a task plugin registry."""
    # Import here to avoid circular imports
    from eos.tasks.base_task import BaseTask

    config = PluginRegistryConfig(
        spec_registry=task_specs,
        base_class=BaseTask,
        config_file_name=TASK_CONFIG_FILE_NAME,
        implementation_file_name=TASK_IMPLEMENTATION_FILE_NAME,
        exception_class=EosTaskPluginError,
        entity_type=EntityType.TASK,
    )
    # Defer loading task plugins; they will be loaded on-demand
    return PluginRegistry(package_manager, config, initialize=False)


def create_device_plugin_registry(
    package_manager: PackageManager,
    device_specs: SpecRegistry,
) -> PluginRegistry:
    """Create a device plugin registry."""
    # Import here to avoid circular imports
    from eos.devices.base_device import BaseDevice

    config = PluginRegistryConfig(
        spec_registry=device_specs,
        base_class=BaseDevice,
        config_file_name=DEVICE_CONFIG_FILE_NAME,
        implementation_file_name=DEVICE_IMPLEMENTATION_FILE_NAME,
        exception_class=EosDevicePluginError,
        entity_type=EntityType.DEVICE,
    )
    return PluginRegistry(package_manager, config, initialize=False)


# =============================================================================
# Campaign Optimizer Plugin Registry
# =============================================================================

CampaignOptimizerCreationFunction = Callable[[], tuple[dict[str, Any], type[AbstractSequentialOptimizer]]]


class CampaignOptimizerPluginRegistry(PluginRegistry[CampaignOptimizerCreationFunction, Any]):
    """
    Responsible for dynamically loading campaign optimizers from all packages
    and providing references to them for later use.
    """

    def __init__(self, package_manager: PackageManager):
        config = PluginRegistryConfig(
            spec_registry=None,  # Campaign optimizers don't use a specification registry
            base_class=None,  # Campaign optimizers don't have a base class
            config_file_name=None,  # Campaign optimizers don't have a separate config file
            implementation_file_name=CAMPAIGN_OPTIMIZER_FILE_NAME,
            exception_class=EosCampaignOptimizerPluginError,
            entity_type=EntityType.EXPERIMENT,
        )
        super().__init__(package_manager, config)

    def get_campaign_optimizer_creation_parameters(
        self, experiment_type: str
    ) -> tuple[dict[str, Any], type[AbstractSequentialOptimizer]] | None:
        """
        Get a function that can be used to get the constructor arguments and the optimizer type so it can be
        constructed later.

        :param experiment_type: The type of the experiment.
        :return: A tuple containing the constructor arguments and the optimizer type, or None if not found.
        """
        optimizer_function = self.get_plugin_class_type(experiment_type)
        if optimizer_function:
            return optimizer_function()
        return None

    def _load_single_plugin(self, package_name: str, dir_path: str, implementation_path: str) -> None:
        log.info(f"Loading campaign optimizer for experiment '{Path(dir_path).name}' from package '{package_name}'.")
        module = self._import_optimizer_module(dir_path, implementation_path)

        experiment_type = Path(dir_path).name
        if not self._register_optimizer_if_valid(module, experiment_type, package_name, implementation_path):
            log.warning(
                f"Optimizer configuration function '{CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME}' not found in the "
                f"campaign optimizer file '{self._config.implementation_file_name}' of experiment "
                f"'{Path(dir_path).name}' in package '{package_name}'."
            )

    def _import_optimizer_module(self, dir_path: str, implementation_path: str) -> object | None:
        """Import the optimizer module from the given path."""
        module_name = Path(dir_path).name
        spec = importlib.util.spec_from_file_location(module_name, implementation_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _register_optimizer_if_valid(
        self,
        module: object,
        experiment_type: str,
        package_name: str,
        implementation_path: str,
    ) -> bool:
        """Register the optimizer if its module contains the required creation function."""
        if CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME not in module.__dict__:
            return False

        optimizer_creator = module.__dict__[CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME]
        self.plugin_types[experiment_type] = optimizer_creator
        self.plugin_modules[experiment_type] = implementation_path

        log.info(f"Loaded campaign optimizer for experiment '{experiment_type}' from package '{package_name}'.")
        return True

    def load_campaign_optimizer(self, experiment_type: str) -> None:
        """
        Load the optimizer configuration function for the given experiment from the appropriate package.
        If the optimizer doesn't exist, log a warning and return without raising an error.
        """
        experiment_package = self._package_manager.find_package_for_entity(experiment_type, EntityType.EXPERIMENT)
        if not experiment_package:
            log.warning(f"No package found for experiment '{experiment_type}'.")
            return

        optimizer_file = (
            self._package_manager.get_entity_dir(experiment_type, EntityType.EXPERIMENT) / CAMPAIGN_OPTIMIZER_FILE_NAME
        )
        if not optimizer_file.exists():
            log.warning(
                f"No campaign optimizer found for experiment '{experiment_type}' in package "
                f"'{experiment_package.name}'."
            )
            return

        self._load_single_plugin(experiment_package.name, experiment_type, optimizer_file)

    def unload_campaign_optimizer(self, experiment_type: str) -> None:
        """
        Unload the optimizer configuration function for the given experiment.
        """
        if experiment_type in self.plugin_types:
            del self.plugin_types[experiment_type]
            del self.plugin_modules[experiment_type]
            log.info(f"Unloaded campaign optimizer for experiment '{experiment_type}'.")

    def reload_plugin(self, experiment_type: str) -> None:
        """
        Reload a specific campaign optimizer by its experiment type.
        """
        self.unload_campaign_optimizer(experiment_type)
        self.load_campaign_optimizer(experiment_type)
        log.info(f"Reloaded campaign optimizer for experiment '{experiment_type}'.")

    def reload_all_plugins(self) -> None:
        """
        Reload all campaign optimizers.
        """
        experiment_types = list(self.plugin_types.keys())
        for experiment_type in experiment_types:
            self.reload_plugin(experiment_type)
        log.info("Reloaded all campaign optimizers.")
