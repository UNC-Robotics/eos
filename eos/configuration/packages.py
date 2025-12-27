from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

import jinja2
import yaml

from eos.configuration.constants import (
    DEVICES_DIR,
    DEVICE_CONFIG_FILE_NAME,
    EXPERIMENTS_DIR,
    EXPERIMENT_CONFIG_FILE_NAME,
    LABS_DIR,
    LAB_CONFIG_FILE_NAME,
    TASKS_DIR,
    TASK_CONFIG_FILE_NAME,
)
from eos.configuration.entities.device_spec_def import DeviceSpecDef
from eos.configuration.entities.experiment_def import ExperimentDef
from eos.configuration.entities.lab_def import LabDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.configuration.exceptions import EosConfigurationError, EosMissingConfigurationError
from eos.logging.logger import log

EntityConfigType = LabDef | ExperimentDef | TaskSpecDef | DeviceSpecDef


class EntityType(Enum):
    LAB = auto()
    EXPERIMENT = auto()
    TASK = auto()
    DEVICE = auto()


@dataclass(frozen=True)
class EntityInfo:
    dir_name: str
    config_file_name: str
    config_type: type[EntityConfigType]


@dataclass(frozen=True)
class EntityLocationInfo:
    package_name: str
    entity_path: str


ENTITY_INFO: dict[EntityType, EntityInfo] = {
    EntityType.LAB: EntityInfo(LABS_DIR, LAB_CONFIG_FILE_NAME, LabDef),
    EntityType.EXPERIMENT: EntityInfo(EXPERIMENTS_DIR, EXPERIMENT_CONFIG_FILE_NAME, ExperimentDef),
    EntityType.TASK: EntityInfo(TASKS_DIR, TASK_CONFIG_FILE_NAME, TaskSpecDef),
    EntityType.DEVICE: EntityInfo(DEVICES_DIR, DEVICE_CONFIG_FILE_NAME, DeviceSpecDef),
}


@dataclass
class Package:
    """A collection of user-defined experiments, labs, devices, tasks, and any code and data."""

    name: str
    path: Path
    _entity_dirs: dict[EntityType, Path] = field(init=False, repr=False)

    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path)
        self._entity_dirs = {entity_type: self.path / info.dir_name for entity_type, info in ENTITY_INFO.items()}

    def get_entity_dir(self, entity_type: EntityType) -> Path:
        return self._entity_dirs[entity_type]


class PackageManager:
    """Manages packages and entity configurations within the user directory."""

    def __init__(self, user_dir: str, allowed_packages: set[str] | None = None):
        self._user_dir = Path(user_dir)
        self._entity_indices: dict[EntityType, dict[str, EntityLocationInfo]] = defaultdict(dict)
        self._packages: dict[str, Package] = {}

        self._discover_packages()
        self._filter_packages(allowed_packages)
        self._validate_packages(allowed_packages)
        self._build_entity_indices()

        log.info(f"Loaded packages: {', '.join(self._packages.keys())}")
        log.debug("Package manager initialized")

    def _discover_packages(self) -> None:
        """Discover EOS packages by recursively searching for directories with pyproject.toml."""
        if not self._user_dir.is_dir():
            raise EosMissingConfigurationError(f"User directory '{self._user_dir}' does not exist")

        self._packages.clear()
        self._scan_directory(self._user_dir)

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

    def _scan_directory(self, directory: Path, depth: int = 0, max_depth: int = 10) -> None:
        """Recursively scan directories to find packages (directories with pyproject.toml)."""
        if not directory.is_dir() or depth > max_depth:
            return

        if (directory / "pyproject.toml").is_file() and directory != self._user_dir:
            self._packages[directory.name] = Package(directory.name, directory)
            log.debug(f"Discovered package: {directory.name} at {directory}")
            return

        for item in directory.iterdir():
            if item.is_dir():
                self._scan_directory(item, depth + 1, max_depth)

    def read_lab(self, lab_name: str) -> LabDef:
        return self._read_entity(lab_name, EntityType.LAB)

    def read_experiment(self, experiment_name: str) -> ExperimentDef:
        return self._read_entity(experiment_name, EntityType.EXPERIMENT)

    def read_task_specs(self) -> tuple[dict[str, TaskSpecDef], dict[str, str]]:
        return self._read_all_entities(EntityType.TASK)

    def read_device_specs(self) -> tuple[dict[str, DeviceSpecDef], dict[str, str]]:
        return self._read_all_entities(EntityType.DEVICE)

    def _read_entity(self, entity_name: str, entity_type: EntityType) -> EntityConfigType:
        location = self._get_entity_location(entity_name, entity_type)
        config_path = self._get_config_file_path(location, entity_type)
        return self._parse_config_file(config_path, entity_type)

    def _read_all_entities(self, entity_type: EntityType) -> tuple[dict[str, EntityConfigType], dict[str, str]]:
        all_entities: dict[str, EntityConfigType] = {}
        all_dirs_to_types: dict[str, str] = {}

        for package in self._packages.values():
            entity_dir = package.get_entity_dir(entity_type)
            if not entity_dir.is_dir():
                continue

            info = ENTITY_INFO[entity_type]
            for config_path in entity_dir.rglob(info.config_file_name):
                subdir = config_path.relative_to(entity_dir).parent
                try:
                    entity = self._parse_config_file(config_path, entity_type)
                    all_entities[entity.type] = entity
                    all_dirs_to_types[Path(package.name) / subdir] = entity.type
                    log.debug(f"Loaded {entity_type.name.lower()} '{entity.type}' from '{subdir}'")
                except EosConfigurationError as e:
                    log.error(f"Error loading {entity_type.name.lower()} from '{config_path}': {e}")
                    raise

        return all_entities, all_dirs_to_types

    def get_package(self, name: str) -> Package | None:
        return self._packages.get(name)

    def get_all_packages(self) -> list[Package]:
        return list(self._packages.values())

    def add_package(self, package_name: str) -> None:
        package_path = self._user_dir / package_name
        if not package_path.is_dir():
            raise EosMissingConfigurationError(f"Package directory '{package_path}' does not exist")

        new_package = Package(package_name, package_path)
        self._packages[package_name] = new_package
        self._index_package(new_package)
        log.info(f"Added package '{package_name}'")

    def remove_package(self, package_name: str) -> None:
        if package_name not in self._packages:
            raise EosMissingConfigurationError(f"Package '{package_name}' not found")

        del self._packages[package_name]
        self._remove_package_from_index(package_name)

        log.info(f"Removed package '{package_name}'")

    def refresh(self) -> None:
        """Re-discover packages and rebuild entity indices."""
        self._discover_packages()
        self._build_entity_indices()
        log.info(f"Refreshed packages: {', '.join(self._packages.keys())}")

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
        for entity_type, info in ENTITY_INFO.items():
            entity_dir = package.get_entity_dir(entity_type)
            for config_path in entity_dir.rglob(info.config_file_name):
                relative_path = config_path.relative_to(entity_dir).parent
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
        path = package.get_entity_dir(entity_type) / entity_location.entity_path / info.config_file_name

        if not path.is_file():
            raise EosMissingConfigurationError(
                f"{entity_type.name.capitalize()} config '{info.config_file_name}' not found for "
                f"'{entity_location.entity_path}'"
            )
        return path

    # Config file parsing

    def _parse_config_file(self, file_path: Path, entity_type: EntityType) -> EntityConfigType:
        """Parse a YAML config file with Jinja2 templating and validate it."""
        info = ENTITY_INFO[entity_type]
        try:
            raw_content = file_path.read_text()
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(self._user_dir),
                undefined=jinja2.StrictUndefined,
                autoescape=True,
            )
            rendered = env.from_string(raw_content).render()
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
