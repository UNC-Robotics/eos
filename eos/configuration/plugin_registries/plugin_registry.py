import inspect
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar
from importlib import util as importlib_util

from eos.configuration.packages.entities import EntityType
from eos.configuration.packages.package_manager import PackageManager
from eos.logging.batch_error_logger import batch_error, raise_batched_errors
from eos.logging.logger import log

T = TypeVar("T")  # Plugin class type
S = TypeVar("S")  # Specification registry type


@dataclass
class PluginRegistryConfig:
    spec_registry: S
    base_class: type[T]
    config_file_name: str | None
    implementation_file_name: str
    not_found_exception_class: type[Exception]
    entity_type: EntityType


class PluginRegistry(Generic[T, S]):
    """A generic registry for dynamically discovering and loading plugin-like implementation classes."""

    def __init__(self, package_manager: PackageManager, config: PluginRegistryConfig):
        self._package_manager = package_manager
        self._config = config
        self._plugin_types: dict[str, type[T]] = {}
        self._plugin_modules: dict[str, str] = {}  # Maps type_name to module path

        self._initialize_registry()

    def get_plugin_class_type(self, type_name: str) -> type[T]:
        if type_name not in self._plugin_types:
            raise self._config.not_found_exception_class(f"Plugin implementation for '{type_name}' not found.")

        return self._plugin_types[type_name]

    def reload_plugin(self, type_name: str) -> None:
        """Reload a specific plugin by type name."""
        if type_name not in self._plugin_modules:
            raise self._config.not_found_exception_class(f"Plugin '{type_name}' not found.")

        module_path = Path(self._plugin_modules[type_name])
        package_name = module_path.parent.parent.name
        dir_path = module_path.parent

        self._load_single_plugin(package_name, dir_path, module_path)
        log.debug(f"Reloaded plugin '{type_name}'")

    def reload_all_plugins(self) -> None:
        """Reload all plugins in the registry."""
        self._initialize_registry()
        log.debug("Reloaded all plugins")

    def _initialize_registry(self) -> None:
        """Load all plugins from all packages."""
        self._plugin_types.clear()
        self._plugin_modules.clear()

        for package in self._package_manager.get_all_packages():
            self._load_package_plugins(package)

        raise_batched_errors(root_exception_type=self._config.not_found_exception_class)

    def _load_package_plugins(self, package) -> None:
        """Load all plugins from a specific package."""
        directory = package.get_entity_dir(self._config.entity_type)
        if not directory.is_dir():
            return

        for current_dir, _, files in os.walk(directory):
            if self._config.config_file_name not in files:
                continue

            current_dir_path = Path(current_dir)
            dir_path = current_dir_path.relative_to(directory)
            implementation_path = current_dir_path / self._config.implementation_file_name

            self._load_single_plugin(package.name, dir_path, implementation_path)

    def _load_single_plugin(self, package_name: str, dir_path: Path, implementation_path: Path) -> None:
        """Load a single plugin from a file."""
        if not implementation_path.exists():
            batch_error(
                f"Implementation file '{implementation_path}' for package '{package_name}' not found.",
                self._config.not_found_exception_class,
            )
            return

        module = self._import_plugin_module(implementation_path, dir_path.name)
        if not module:
            return

        implementation_class = self._extract_implementation_class(module, package_name)
        if not implementation_class:
            return

        self._register_plugin(implementation_class, package_name, dir_path, implementation_path)

    def _import_plugin_module(self, implementation_path: Path, module_name: str) -> object | None:
        """Import a module from a file."""
        try:
            spec = importlib_util.spec_from_file_location(module_name, implementation_path)
            module = importlib_util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            batch_error(
                f"Failed to load module '{module_name}' from '{implementation_path}': {e!s}",
                self._config.not_found_exception_class,
            )
            return None

    def _extract_implementation_class(self, module: object, package_name: str) -> type[T] | None:
        """Find and extract the implementation class in a module."""
        implementation_classes = self._find_implementation_classes(module)

        if not implementation_classes:
            batch_error(
                f"No implementation class inheriting from '{self._config.base_class.__name__}' found in "
                f"'{module}' in package '{package_name}'.",
                self._config.not_found_exception_class,
            )
            return None

        if len(implementation_classes) > 1:
            batch_error(
                f"Multiple implementation classes found in '{module}' in package '{package_name}': "
                f"{', '.join(implementation_classes)}. Each module should contain exactly one implementation class.",
                self._config.not_found_exception_class,
            )
            return None

        return implementation_classes[0]

    def _find_implementation_classes(self, module: object) -> list[type[T]]:
        return [
            obj
            for _, obj in module.__dict__.items()
            if (
                inspect.isclass(obj) and obj is not self._config.base_class and issubclass(obj, self._config.base_class)
            )
        ]

    def _register_plugin(
        self, implementation_class: type[T], package_name: str, dir_path: Path, implementation_file: Path
    ) -> None:
        """Register a loaded plugin in the registry."""
        type_name = self._config.spec_registry.get_spec_by_dir(Path(package_name) / dir_path)
        self._plugin_types[type_name] = implementation_class
        self._plugin_modules[type_name] = str(implementation_file)

        log.debug(
            f"Loaded plugin class '{implementation_class.__name__}' "
            f"for type '{type_name}' from package '{package_name}'"
        )
