from abc import ABC, abstractmethod

from eos.configuration.entities.experiment import (
    ExperimentConfig,
)
from eos.configuration.entities.lab import LabConfig
from eos.configuration.entities.task import TaskConfig
from eos.configuration.spec_registries.task_spec_registry import (
    TaskSpecRegistry,
)


class BaseTaskSequenceValidator(ABC):
    def __init__(
        self,
        experiment_config: ExperimentConfig,
        lab_configs: list[LabConfig],
    ):
        self._experiment_config = experiment_config
        self._lab_configs = lab_configs
        self._tasks = TaskSpecRegistry()

    @abstractmethod
    def validate(self) -> None:
        pass

    def _find_task_by_id(self, task_id: str) -> TaskConfig | None:
        return next((task for task in self._experiment_config.tasks if task.id == task_id), None)
