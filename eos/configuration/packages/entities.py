from dataclasses import dataclass
from enum import Enum, auto

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
