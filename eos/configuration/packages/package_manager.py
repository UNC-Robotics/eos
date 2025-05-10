from pathlib import Path

from eos.configuration.entities.device_spec import DeviceSpec
from eos.configuration.entities.experiment import ExperimentConfig
from eos.configuration.entities.lab import LabConfig
from eos.configuration.entities.task_spec import TaskSpecConfig
from eos.configuration.exceptions import EosMissingConfigurationError
from eos.configuration.packages.entities import EntityType, EntityLocationInfo, ENTITY_INFO, EntityConfigType
from eos.configuration.packages.entity_index import EntityIndex
from eos.configuration.packages.entity_reader import EntityReader
from eos.configuration.packages.package import Package
from eos.configuration.packages.package_validator import PackageValidator
from eos.logging.logger import log


class PackageManager:
    """
    Manages packages and entity configurations within the user directory.
    """

    def __init__(self, user_dir: str):
        self._user_dir = Path(user_dir)
        self._entity_reader = EntityReader(self._user_dir)
        self._entity_index = EntityIndex()

        self._packages: dict[str, Package] = {}
        self._discover_packages()

        PackageValidator(self._user_dir, self._packages).validate()
        self._entity_index.build_indices(self._packages)
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
        entity_location = self._entity_index.get_entity_location(entity_name, entity_type)
        config_file_path = self._get_config_file_path(entity_location, entity_type)
        return self._entity_reader.read_entity(config_file_path, entity_type)

    def _read_all_entity_configs(self, entity_type: EntityType) -> tuple[dict[str, EntityConfigType], dict[str, str]]:
        all_configs = {}
        all_dirs_to_types = {}
        for package in self._packages.values():
            entity_dir = package.get_entity_dir(entity_type)
            if not entity_dir.is_dir():
                continue
            configs, dirs_to_types = self._entity_reader.read_all_entities(str(entity_dir), entity_type)
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
        PackageValidator(self._user_dir, {package_name: new_package}).validate()

        self._packages[package_name] = new_package
        self._entity_index.add_package(new_package)

        log.info(f"Added package '{package_name}'")

    def remove_package(self, package_name: str) -> None:
        if package_name not in self._packages:
            raise EosMissingConfigurationError(f"Package '{package_name}' not found")

        del self._packages[package_name]
        self._entity_index.remove_package(package_name)

        log.info(f"Removed package '{package_name}'")

    def find_package_for_entity(self, entity_name: str, entity_type: EntityType) -> Package | None:
        entity_location = self._entity_index.get_entity_location(entity_name, entity_type)
        return self._packages.get(entity_location.package_name) if entity_location else None

    def get_entity_dir(self, entity_name: str, entity_type: EntityType) -> Path:
        entity_location = self._entity_index.get_entity_location(entity_name, entity_type)
        package = self._packages[entity_location.package_name]
        return package.get_entity_dir(entity_type) / entity_location.entity_path

    def get_entities_in_package(self, package_name: str, entity_type: EntityType) -> list[str]:
        return self._entity_index.get_entities_in_package(package_name, entity_type)

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
