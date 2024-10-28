from eos.configuration.entities.experiment import ExperimentConfig
from eos.configuration.entities.lab import LabConfig
from eos.configuration.exceptions import EosExperimentConfigurationError
from eos.configuration.validation.experiment_container_validator import (
    ExperimentContainerValidator,
)

from eos.configuration.validation.task_sequence_validator import (
    TaskSequenceValidator,
)


class ExperimentValidator:
    def __init__(
        self,
        experiment_config: ExperimentConfig,
        lab_configs: list[LabConfig],
    ):
        self._experiment_config = experiment_config
        self._lab_configs = lab_configs

    def validate(self) -> None:
        self._validate_labs()
        ExperimentContainerValidator(self._experiment_config, self._lab_configs).validate()
        TaskSequenceValidator(self._experiment_config, self._lab_configs).validate()

    def _validate_labs(self) -> None:
        lab_types = [lab.type for lab in self._lab_configs]
        invalid_labs = []
        for lab in self._experiment_config.labs:
            if lab not in lab_types:
                invalid_labs.append(lab)

        if invalid_labs:
            invalid_labs_str = "\n  ".join(invalid_labs)
            raise EosExperimentConfigurationError(
                f"The following labs required by experiment '{self._experiment_config.type}' do not exist:"
                f"\n  {invalid_labs_str}"
            )
