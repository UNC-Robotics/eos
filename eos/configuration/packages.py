import importlib
import importlib.machinery
import importlib.util
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from types import ModuleType

import jinja2
import ray.cloudpickle
import yaml

from eos.configuration.constants import (
    DEVICES_DIR,
    DEVICE_FILE_NAME,
    PROTOCOLS_DIR,
    PROTOCOL_CONFIG_FILE_NAME,
    LABS_DIR,
    LAB_CONFIG_FILE_NAME,
    TASKS_DIR,
    TASK_FILE_NAME,
)
from eos.configuration.entities.protocol_def import ProtocolDef
from eos.configuration.entities.lab_def import LabDef
from eos.configuration.exceptions import EosConfigurationError, EosMissingConfigurationError
from eos.logging.logger import log

EntityConfigType = LabDef | ProtocolDef


class EntityType(Enum):
    LAB = auto()
    PROTOCOL = auto()
    TASK = auto()
    DEVICE = auto()


@dataclass(frozen=True)
class EntityInfo:
    dir_name: str
    file_name: str
    config_type: type[EntityConfigType] | None = None


@dataclass(frozen=True)
class EntityLocationInfo:
    package_name: str
    entity_path: str


ENTITY_INFO: dict[EntityType, EntityInfo] = {
    EntityType.LAB: EntityInfo(LABS_DIR, LAB_CONFIG_FILE_NAME, LabDef),
    EntityType.PROTOCOL: EntityInfo(PROTOCOLS_DIR, PROTOCOL_CONFIG_FILE_NAME, ProtocolDef),
    EntityType.TASK: EntityInfo(TASKS_DIR, TASK_FILE_NAME),
    EntityType.DEVICE: EntityInfo(DEVICES_DIR, DEVICE_FILE_NAME),
}


@dataclass
class Package:
    """A collection of user-defined protocols, labs, devices, tasks, and any code and data."""

    name: str
    path: Path
    _entity_dirs: dict[EntityType, Path] = field(init=False, repr=False)

    def __post_init__(self):
        self.path = Path(self.path).resolve()
        self._entity_dirs = {entity_type: self.path / info.dir_name for entity_type, info in ENTITY_INFO.items()}

    def get_entity_dir(self, entity_type: EntityType) -> Path:
        return self._entity_dirs[entity_type]


def discover_packages(user_dir: Path, max_depth: int = 10) -> dict[str, Package]:
    """Recursively scan ``user_dir`` for packages (directories containing ``pyproject.toml``).

    Raises ``EosConfigurationError`` if two packages share the same directory name — the error
    lists all conflicting paths so the user can resolve the clash.
    """
    found: dict[str, list[Path]] = defaultdict(list)

    def scan(current: Path, depth: int) -> None:
        if not current.is_dir() or depth > max_depth:
            return
        if (current / "pyproject.toml").is_file() and current != user_dir:
            found[current.name].append(current)
            return
        for item in current.iterdir():
            if item.is_dir():
                scan(item, depth + 1)

    scan(user_dir, 0)

    duplicates = {name: paths for name, paths in found.items() if len(paths) > 1}
    if duplicates:
        detail = "\n".join(
            f"  '{name}': {', '.join(str(p) for p in paths)}" for name, paths in sorted(duplicates.items())
        )
        raise EosConfigurationError(f"Duplicate package names in '{user_dir}':\n{detail}")

    return {name: Package(name, paths[0]) for name, paths in found.items()}


class PackageManager:
    """Manages packages and entity configurations within the user directory."""

    def __init__(self, user_dir: str, allowed_packages: set[str] | None = None):
        self._user_dir = Path(user_dir).resolve()
        self._allowed_packages = set(allowed_packages) if allowed_packages else None
        self._entity_indices: dict[EntityType, dict[str, EntityLocationInfo]] = defaultdict(dict)
        self._packages: dict[str, Package] = {}
        self._jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self._user_dir),
            undefined=jinja2.StrictUndefined,
            autoescape=True,
        )

        self._discover_packages()
        self._filter_packages(self._allowed_packages)
        self._validate_packages(self._allowed_packages)
        self._build_entity_indices()

        log.info(f"Loaded packages: {', '.join(self._packages.keys())}")
        log.debug("Package manager initialized")

    def _discover_packages(self) -> None:
        """Discover EOS packages by recursively searching for directories with pyproject.toml."""
        if not self._user_dir.is_dir():
            raise EosMissingConfigurationError(f"User directory '{self._user_dir}' does not exist")

        self._packages = discover_packages(self._user_dir)

        if not self._packages:
            log.warning(f"No valid packages found in {self._user_dir}")

    def _filter_packages(self, allowed_packages: set[str] | None) -> None:
        """Filter packages to only include allowed ones."""
        if not allowed_packages:
            return
        ignored = [name for name in self._packages if name not in allowed_packages]
        self._packages = {name: pkg for name, pkg in self._packages.items() if name in allowed_packages}
        if ignored:
            log.info(f"Ignoring packages: {', '.join(ignored)}")

    def _validate_packages(self, allowed_packages: set[str] | None) -> None:
        """Validate that at least one package exists."""
        if self._packages:
            return
        if allowed_packages:
            raise EosMissingConfigurationError(
                f"No valid packages found in '{self._user_dir}' matching: {', '.join(allowed_packages)}"
            )
        raise EosMissingConfigurationError(f"No valid packages found in '{self._user_dir}'")

    def read_lab(self, lab_name: str) -> LabDef:
        return self._read_entity(lab_name, EntityType.LAB)

    def read_protocol(self, protocol_run_name: str) -> ProtocolDef:
        return self._read_entity(protocol_run_name, EntityType.PROTOCOL)

    def _read_entity(self, entity_name: str, entity_type: EntityType) -> EntityConfigType:
        location = self._get_entity_location(entity_name, entity_type)
        config_path = self._get_config_file_path(location, entity_type)
        return self._parse_config_file(config_path, entity_type)

    @staticmethod
    def find_entity_dirs(package: Package, entity_type: EntityType) -> list[Path]:
        """Return the entity directories of a package, relative to its entity type directory."""
        entity_dir = package.get_entity_dir(entity_type)
        file_name = ENTITY_INFO[entity_type].file_name
        found = []
        for root, dirs, files in os.walk(entity_dir):
            if file_name in files and Path(root) != entity_dir:
                found.append(Path(root).relative_to(entity_dir))
                dirs.clear()  # Files nested inside an entity belong to it
            else:
                dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]
        return sorted(found)

    def import_module(self, package: Package, relative_path: Path, *, fresh: bool = False) -> ModuleType:
        """Import a module of a package by its path relative to the package root. ``fresh`` re-reads the module."""
        self._make_importable(package)
        module_name = ".".join([package.name, *relative_path.with_suffix("").parts])
        if fresh:
            sys.modules.pop(module_name, None)
        return importlib.import_module(module_name)

    def purge_modules(self, package: Package | None = None) -> None:
        """Forget imported modules of one or all packages so the next import re-reads them from disk."""
        for purged in [package] if package else list(self._packages.values()):
            root = sys.modules.get(purged.name)
            if root is None or list(getattr(root, "__path__", [])) != [str(purged.path)]:
                continue  # Not imported, or a different module of the same name
            prefix = f"{purged.name}."
            for module_name in [name for name in list(sys.modules) if name == purged.name or name.startswith(prefix)]:
                del sys.modules[module_name]
        importlib.invalidate_caches()

    @staticmethod
    def _make_importable(package: Package) -> None:
        """Register a package as a top-level Python package that Ray pickles by value."""
        module = sys.modules.get(package.name)
        if module is None:
            found = importlib.util.find_spec(package.name)
            locations = None if found is None else found.submodule_search_locations or []
        else:
            locations = getattr(module, "__path__", [])
        if locations is not None and package.path not in [Path(location) for location in locations]:
            raise EosConfigurationError(f"Package name '{package.name}' clashes with another Python module.")
        if module is not None:
            return

        init_file = package.path / "__init__.py"
        if init_file.is_file():
            spec = importlib.util.spec_from_file_location(
                package.name, init_file, submodule_search_locations=[str(package.path)]
            )
        else:
            spec = importlib.machinery.ModuleSpec(package.name, None, is_package=True)
            spec.submodule_search_locations = [str(package.path)]

        module = importlib.util.module_from_spec(spec)
        sys.modules[package.name] = module
        try:
            if spec.loader is not None:
                spec.loader.exec_module(module)
        except Exception:
            del sys.modules[package.name]
            raise
        ray.cloudpickle.register_pickle_by_value(module)

    def get_package(self, name: str) -> Package | None:
        return self._packages.get(name)

    def get_all_packages(self) -> list[Package]:
        return list(self._packages.values())

    def add_package(self, package_name: str) -> None:
        discovered = discover_packages(self._user_dir)
        if package_name not in discovered:
            raise EosMissingConfigurationError(f"Package directory '{self._user_dir / package_name}' does not exist")

        new_package = discovered[package_name]
        self._packages[package_name] = new_package
        self._index_package(new_package)

        if self._allowed_packages is not None:
            self._allowed_packages.add(package_name)

        log.info(f"Added package '{package_name}'")

    def remove_package(self, package_name: str) -> None:
        if package_name not in self._packages:
            raise EosMissingConfigurationError(f"Package '{package_name}' not found")

        self.purge_modules(self._packages.pop(package_name))
        self._remove_package_from_index(package_name)

        if self._allowed_packages is not None:
            self._allowed_packages.discard(package_name)

        log.info(f"Removed package '{package_name}'")

    def refresh(self) -> None:
        """Re-discover packages and rebuild entity indices."""
        self.purge_modules()
        self._discover_packages()
        self._filter_packages(self._allowed_packages)
        self._build_entity_indices()
        log.info(f"Refreshed packages: {', '.join(self._packages.keys())}")

    def discover_all_package_names(self) -> list[str]:
        """Scan the filesystem and return all package names without modifying state."""
        return sorted(discover_packages(self._user_dir).keys())

    def find_package_for_entity(self, entity_name: str, entity_type: EntityType) -> Package | None:
        entity_location = self._get_entity_location(entity_name, entity_type)
        return self._packages.get(entity_location.package_name) if entity_location else None

    def get_entity_dir(self, entity_name: str, entity_type: EntityType) -> Path:
        entity_location = self._get_entity_location(entity_name, entity_type)
        package = self._packages[entity_location.package_name]
        return package.get_entity_dir(entity_type) / entity_location.entity_path

    def get_entities_in_package(self, package_name: str, entity_type: EntityType) -> list[str]:
        """Get all entities of a given type in a package."""
        return [name for name, loc in self._entity_indices[entity_type].items() if loc.package_name == package_name]

    # Entity indexing methods

    def _build_entity_indices(self) -> None:
        """Build entity indices for all packages."""
        self._entity_indices.clear()
        for package in self._packages.values():
            self._index_package(package)

    def _remove_package_from_index(self, package_name: str) -> None:
        """Remove a package from the entity index."""
        for entity_type in self._entity_indices:
            self._entity_indices[entity_type] = {
                name: loc for name, loc in self._entity_indices[entity_type].items() if loc.package_name != package_name
            }

    def _index_package(self, package: Package) -> None:
        """Index all entities in a package."""
        for entity_type in ENTITY_INFO:
            for relative_path in self.find_entity_dirs(package, entity_type):
                entity_name = relative_path.name

                existing = self._entity_indices[entity_type].get(entity_name)
                if existing and existing.package_name != package.name:
                    raise EosConfigurationError(
                        f"Duplicate {entity_type.name.lower()} '{entity_name}' in packages "
                        f"'{existing.package_name}' and '{package.name}'"
                    )
                self._entity_indices[entity_type][entity_name] = EntityLocationInfo(package.name, str(relative_path))

    def _get_entity_location(self, entity_name: str, entity_type: EntityType) -> EntityLocationInfo:
        """Get the location of an entity."""
        if entity_name not in self._entity_indices[entity_type]:
            raise EosMissingConfigurationError(f"{entity_type.name.capitalize()} '{entity_name}' not found")
        return self._entity_indices[entity_type][entity_name]

    def _get_config_file_path(self, entity_location: EntityLocationInfo, entity_type: EntityType) -> Path:
        """Get the config file path for an entity."""
        info = ENTITY_INFO[entity_type]
        package = self._packages[entity_location.package_name]
        path = package.get_entity_dir(entity_type) / entity_location.entity_path / info.file_name

        if not path.is_file():
            raise EosMissingConfigurationError(
                f"{entity_type.name.capitalize()} config '{info.file_name}' not found for "
                f"'{entity_location.entity_path}'"
            )
        return path

    # Config file parsing

    def _parse_config_file(self, file_path: Path, entity_type: EntityType) -> EntityConfigType:
        """Parse a YAML config file with Jinja2 templating and validate it."""
        info = ENTITY_INFO[entity_type]
        try:
            raw_content = file_path.read_text()
            rendered = self._jinja_env.from_string(raw_content).render()
            data = yaml.safe_load(rendered)
            return info.config_type.model_validate(data)
        except OSError as e:
            raise EosConfigurationError(f"Error reading '{file_path}': {e}") from e
        except yaml.YAMLError as e:
            raise EosConfigurationError(f"Error parsing YAML in '{file_path}': {e}") from e
        except jinja2.exceptions.TemplateError as e:
            raise EosConfigurationError(f"Jinja2 template error in '{file_path}': {e}") from e
        except Exception as e:
            raise EosConfigurationError(f"Error processing {entity_type.name.lower()} config '{file_path}': {e}") from e
