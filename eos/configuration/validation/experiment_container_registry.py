from eos.configuration.entities.experiment import (
    ExperimentConfig,
)
from eos.configuration.entities.lab import (
    LabConfig,
    LabContainerConfig,
)


class ExperimentContainerRegistry:
    """
    The container registry stores information about the containers in the labs used by an experiment.
    """

    def __init__(self, experiment_config: ExperimentConfig, lab_configs: list[LabConfig]):
        self._experiment_config = experiment_config
        self._lab_configs = [lab for lab in lab_configs if lab.type in self._experiment_config.labs]

    def find_container_by_id(self, container_id: str) -> LabContainerConfig | None:
        """
        Find a container in the lab by its id.
        """
        for lab in self._lab_configs:
            for container in lab.containers:
                if container_id in container.ids:
                    return container

        return None
