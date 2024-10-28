from eos.configuration.entities.experiment import (
    ExperimentConfig,
    ExperimentContainerConfig,
)
from eos.configuration.entities.lab import LabConfig
from eos.configuration.exceptions import EosContainerConfigurationError
from eos.configuration.validation.experiment_container_registry import ExperimentContainerRegistry


class ExperimentContainerValidator:
    """
    Validate the containers of an experiment.
    """

    def __init__(self, experiment_config: ExperimentConfig, lab_configs: list[LabConfig]):
        self._experiment_config = experiment_config
        self._lab_configs = lab_configs

        self._container_registry = ExperimentContainerRegistry(experiment_config, lab_configs)

    def validate(self) -> None:
        self._validate_containers()

    def _validate_containers(self) -> None:
        if not self._experiment_config.containers:
            return

        for container in self._experiment_config.containers:
            self._validate_container_exists(container)

    def _validate_container_exists(self, container: ExperimentContainerConfig) -> None:
        for lab in self._lab_configs:
            for lab_container in lab.containers:
                if container.id in lab_container.ids:
                    return

        raise EosContainerConfigurationError(f"Container '{container.id}' does not exist.")
