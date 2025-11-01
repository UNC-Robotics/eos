import inspect
import os
import sys
from dataclasses import dataclass
from importlib import util as importlib_util
from pathlib import Path
from typing import Generic, TypeVar

from eos.configuration.packages.entities import EntityType
from eos.configuration.packages.package_manager import PackageManager
from eos.logging.batch_error_logger import batch_error, raise_batched_errors
from eos.logging.logger import log

T = TypeVar("T")  # plugin class type
S = TypeVar("S")  # spec registry type


@dataclass(frozen=True)
class PluginRegistryConfig(Generic[T, S]):
    spec_registry: S
    base_class: type[T]
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
