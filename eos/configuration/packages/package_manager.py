import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import jinja2
import yaml

from eos.configuration.entities.device_spec import DeviceSpec
from eos.configuration.entities.experiment import ExperimentConfig
from eos.configuration.entities.lab import LabConfig
from eos.configuration.entities.task_spec import TaskSpecConfig
from eos.configuration.exceptions import EosMissingConfigurationError, EosConfigurationError
from eos.configuration.packages.entities import EntityType, EntityLocationInfo, ENTITY_INFO, EntityConfigType, Package
from eos.logging.logger import log


class PackageManager:
    """
    Manages packages and entity configurations within the user directory.
    """

    def __init__(self, user_dir: str):
        self._user_dir = Path(user_dir)
        self._entity_indices: dict[EntityType, dict[str, EntityLocationInfo]] = defaultdict(dict)

        self._packages: dict[str, Package] = {}
        self._discover_packages()

        # Validate packages
        if not self._packages:
            raise EosMissingConfigurationError(f"No valid packages found in the user directory '{self._user_dir}'")

        self._build_entity_indices(self._packages)
        log.info(f"Found packages: {', '.join(self._packages.keys())}")

        log.debug("Package manager initialized")

    def _discover_packages(self) -> None:
        """
        Discover EOS packages in the user directory by recursively searching for directories
        containing pyproject.toml files.
        """
        if not self._user_dir.is_dir():
            raise EosMissingConfigurationError(f"User directory '{self._user_dir}' does not exist")

        self._packages = {}
        self._scan_directory(self._user_dir)

        if not self._packages:
            log.warning(f"No valid packages found in {self._user_dir}")

    def _scan_directory(self, directory: Path, max_depth: int = 10, current_depth: int = 0) -> None:
        """
        Recursively scan directories to find packages (directories with pyproject.toml files).
        """
        # Stop conditions
        if not directory.is_dir() or current_depth > max_depth:
            return

        # Check if current directory is a package (but not the user directory itself)
        pyproject_path = directory / "pyproject.toml"
        if pyproject_path.is_file() and directory != self._user_dir:
            # Add as package and don't scan deeper
            package_name = directory.name
            self._packages[package_name] = Package(package_name, str(directory))
            log.debug(f"Discovered package: {package_name} at {directory}")
            return

        # Scan subdirectories
        for item in directory.iterdir():
            if item.is_dir():
                self._scan_directory(item, max_depth, current_depth + 1)

    def read_lab_config(self, lab_name: str) -> LabConfig:
        return self._read_entity_config(lab_name, EntityType.LAB)

    def read_experiment_config(self, experiment_name: str) -> ExperimentConfig:
        return self._read_entity_config(experiment_name, EntityType.EXPERIMENT)

    def read_task_configs(self) -> tuple[dict[str, TaskSpecConfig], dict[str, str]]:
        return self._read_all_entity_configs(EntityType.TASK)

    def read_device_configs(self) -> tuple[dict[str, DeviceSpec], dict[str, str]]:
        return self._read_all_entity_configs(EntityType.DEVICE)

    def _read_entity_config(self, entity_name: str, entity_type: EntityType) -> EntityConfigType:
        entity_location = self._get_entity_location(entity_name, entity_type)
        config_file_path = self._get_config_file_path(entity_location, entity_type)
        return self._read_entity(config_file_path, entity_type)

    def _read_all_entity_configs(self, entity_type: EntityType) -> tuple[dict[str, EntityConfigType], dict[str, str]]:
        all_configs = {}
        all_dirs_to_types = {}
        for package in self._packages.values():
            entity_dir = package.get_entity_dir(entity_type)
            if not entity_dir.is_dir():
                continue
            configs, dirs_to_types = self._read_all_entities(str(entity_dir), entity_type)
            all_configs.update(configs)
            all_dirs_to_types.update({Path(package.name) / k: v for k, v in dirs_to_types.items()})
        return all_configs, all_dirs_to_types

    def get_package(self, name: str) -> Package | None:
        return self._packages.get(name)

    def get_all_packages(self) -> list[Package]:
        return list(self._packages.values())

    def add_package(self, package_name: str) -> None:
        package_path = Path(self._user_dir) / package_name
        if not package_path.is_dir():
            raise EosMissingConfigurationError(f"Package directory '{package_path}' does not exist")

        new_package = Package(package_name, str(package_path))

        self._packages[package_name] = new_package
        self._add_package_to_index(new_package)

        log.info(f"Added package '{package_name}'")

    def remove_package(self, package_name: str) -> None:
        if package_name not in self._packages:
            raise EosMissingConfigurationError(f"Package '{package_name}' not found")

        del self._packages[package_name]
        self._remove_package_from_index(package_name)

        log.info(f"Removed package '{package_name}'")

    def find_package_for_entity(self, entity_name: str, entity_type: EntityType) -> Package | None:
        entity_location = self._get_entity_location(entity_name, entity_type)
        return self._packages.get(entity_location.package_name) if entity_location else None

    def get_entity_dir(self, entity_name: str, entity_type: EntityType) -> Path:
        entity_location = self._get_entity_location(entity_name, entity_type)
        package = self._packages[entity_location.package_name]
        return package.get_entity_dir(entity_type) / entity_location.entity_path

    def get_entities_in_package(self, package_name: str, entity_type: EntityType) -> list[str]:
        return self._get_entities_in_package(package_name, entity_type)

    def _get_config_file_path(self, entity_location: EntityLocationInfo, entity_type: EntityType) -> str:
        entity_info = ENTITY_INFO[entity_type]
        package = self._packages[entity_location.package_name]
        config_file_path = (
            package.get_entity_dir(entity_type) / entity_location.entity_path / entity_info.config_file_name
        )

        if not config_file_path.is_file():
            raise EosMissingConfigurationError(
                f"{entity_type.name.capitalize()} file '{entity_info.config_file_name}' does not exist for "
                f"'{entity_location.entity_path}'",
                EosMissingConfigurationError,
            )

        return str(config_file_path)

    # Entity indexing methods

    def _build_entity_indices(self, packages: dict[str, Package]) -> None:
        """Build entity indices for all packages."""
        self._entity_indices.clear()
        for package in packages.values():
            self._index_package(package)

    def _add_package_to_index(self, package: Package) -> None:
        """Add a package to the entity index."""
        self._index_package(package)

    def _remove_package_from_index(self, package_name: str) -> None:
        """Remove a package from the entity index."""
        for entity_type in self._entity_indices:
            self._entity_indices[entity_type] = {
                entity_name: location
                for entity_name, location in self._entity_indices[entity_type].items()
                if location.package_name != package_name
            }

    def _index_package(self, package: Package) -> None:
        """Index all entities in a package."""
        for entity_type in EntityType:
            entity_dir = package.get_entity_dir(entity_type)
            config_file_name = ENTITY_INFO[entity_type].config_file_name

            for entity_path in entity_dir.rglob(config_file_name):
                relative_path = entity_path.relative_to(entity_dir).parent
                entity_name = relative_path.name
                self._entity_indices[entity_type][entity_name] = EntityLocationInfo(package.name, str(relative_path))

    def _get_entity_location(self, entity_name: str, entity_type: EntityType) -> EntityLocationInfo:
        """Get the location of an entity."""
        try:
            return self._entity_indices[entity_type][entity_name]
        except KeyError as e:
            raise EosMissingConfigurationError(f"{entity_type.name.capitalize()} '{entity_name}' not found") from e

    def _get_entities_in_package(self, package_name: str, entity_type: EntityType) -> list[str]:
        """Get all entities of a given type in a package."""
        return [
            entity_name
            for entity_name, location in self._entity_indices[entity_type].items()
            if location.package_name == package_name
        ]

    # Entity reading methods

    def _read_entity(self, file_path: str, entity_type: EntityType) -> EntityConfigType:
        """Read and parse an entity configuration file."""
        return self._read_config(file_path, ENTITY_INFO[entity_type].config_type, f"{entity_type.name}")

    def _read_all_entities(
        self, base_dir: str, entity_type: EntityType
    ) -> tuple[dict[str, EntityConfigType], dict[Path, str]]:
        """Read all entity configurations in a directory."""
        entity_info = ENTITY_INFO[entity_type]
        configs = {}
        dirs_to_types = {}

        for root, _, files in os.walk(base_dir):
            if entity_info.config_file_name not in files:
                continue

            entity_subdir = Path(root).relative_to(base_dir)
            config_file_path = Path(root) / entity_info.config_file_name

            try:
                structured_config = self._read_entity(str(config_file_path), entity_type)
                entity_type_name = structured_config.type
                configs[entity_type_name] = structured_config
                dirs_to_types[entity_subdir] = entity_type_name

                log.debug(
                    f"Loaded {entity_type.name.capitalize()} specification from directory '{entity_subdir}' of type "
                    f"'{entity_type_name}'"
                )
                log.debug(f"{entity_type.name.capitalize()} configuration '{entity_type_name}': {structured_config}")
            except EosConfigurationError as e:
                log.error(f"Error loading {entity_type.name.lower()} configuration from '{config_file_path}': {e}")
                raise

        return configs, dirs_to_types

    def _read_config(self, file_path: str, config_type: type[EntityConfigType], config_name: str) -> EntityConfigType:
        """Read and validate a configuration file."""
        try:
            config_data = self._render_jinja_yaml(file_path)
            return config_type.model_validate(config_data)
        except OSError as e:
            raise EosConfigurationError(f"Error reading configuration file '{file_path}': {e!s}") from e
        except jinja2.exceptions.TemplateError as e:
            raise EosConfigurationError(f"Error in Jinja2 template for '{config_name.lower()}': {e!s}") from e
        except Exception as e:
            raise EosConfigurationError(f"Error processing {config_name.lower()} configuration: {e!s}") from e

    def _render_jinja_yaml(self, file_path: str) -> dict[str, Any]:
        """Render a YAML file with Jinja2 templating."""
        try:
            with Path(file_path).open() as f:
                raw_content = f.read()
        except OSError as e:
            raise EosConfigurationError(f"Error reading file '{file_path}': {e}") from e

        try:
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(Path(self._user_dir)),  # user directory
                undefined=jinja2.StrictUndefined,
                autoescape=True,
            )

            template = env.from_string(raw_content)
            rendered_content = template.render()

            return yaml.safe_load(rendered_content)
        except yaml.YAMLError as e:
            raise EosConfigurationError(f"Error parsing YAML in {file_path}: {e}") from e
        except jinja2.exceptions.TemplateError as e:
            raise EosConfigurationError(f"Error in Jinja2 template processing: {e}") from e
