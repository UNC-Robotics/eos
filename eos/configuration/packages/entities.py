from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import ClassVar

from eos.configuration.constants import (
    LABS_DIR,
    LAB_CONFIG_FILE_NAME,
    EXPERIMENTS_DIR,
    EXPERIMENT_CONFIG_FILE_NAME,
    TASKS_DIR,
    TASK_CONFIG_FILE_NAME,
    DEVICES_DIR,
    DEVICE_CONFIG_FILE_NAME,
)
from eos.configuration.entities.device_spec import DeviceSpec
from eos.configuration.entities.experiment import ExperimentConfig
from eos.configuration.entities.lab import LabConfig
from eos.configuration.entities.task_spec import TaskSpecConfig

EntityConfigType = LabConfig | ExperimentConfig | TaskSpecConfig | DeviceSpec


class EntityType(Enum):
    LAB = auto()
    EXPERIMENT = auto()
    TASK = auto()
    DEVICE = auto()


@dataclass
class EntityInfo:
    dir_name: str
    config_file_name: str
    config_type: type[EntityConfigType]


@dataclass
class EntityLocationInfo:
    package_name: str
    entity_path: str


ENTITY_INFO: dict[EntityType, EntityInfo] = {
    EntityType.LAB: EntityInfo(LABS_DIR, LAB_CONFIG_FILE_NAME, LabConfig),
    EntityType.EXPERIMENT: EntityInfo(EXPERIMENTS_DIR, EXPERIMENT_CONFIG_FILE_NAME, ExperimentConfig),
    EntityType.TASK: EntityInfo(TASKS_DIR, TASK_CONFIG_FILE_NAME, TaskSpecConfig),
    EntityType.DEVICE: EntityInfo(DEVICES_DIR, DEVICE_CONFIG_FILE_NAME, DeviceSpec),
}


@dataclass
class Package:
    """
    A collection of user-defined experiments, labs, devices, tasks, and any code and data.
    """

    name: str
    path: Path
    entity_dirs: dict[EntityType, Path] = field(init=False, repr=False)

    ENTITY_DIR_MAP: ClassVar = {
        EntityType.EXPERIMENT: EXPERIMENTS_DIR,
        EntityType.LAB: LABS_DIR,
        EntityType.DEVICE: DEVICES_DIR,
        EntityType.TASK: TASKS_DIR,
    }

    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path)
        self.entity_dirs = {entity_type: self.path / dir_name for entity_type, dir_name in self.ENTITY_DIR_MAP.items()}

    def get_entity_dir(self, entity_type: EntityType) -> Path:
        return self.entity_dirs[entity_type]
