from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task import TaskConfig
from eos.configuration.entities.task_spec import TaskSpecConfig
from eos.tasks.validation.task_device_validator import TaskDeviceValidator
from eos.tasks.validation.task_input_parameter_validator import TaskInputParameterValidator


class TaskValidator:
    def __init__(self, configuration_manager: ConfigurationManager):
        self.configuration_manager = configuration_manager
        self.task_specs = configuration_manager.task_specs

    def validate(self, task_config: TaskConfig) -> None:
        task_spec = self.task_specs.get_spec_by_type(task_config.type)
        self._validate_devices(task_config, task_spec)
        self._validate_parameters(task_config, task_spec)

    def _validate_devices(self, task_config: TaskConfig, task_spec: TaskSpecConfig) -> None:
        validator = TaskDeviceValidator(task_config, task_spec, self.configuration_manager)
        validator.validate()

    def _validate_parameters(self, task_config: TaskConfig, task_spec: TaskSpecConfig) -> None:
        validator = TaskInputParameterValidator(task_config, task_spec)
        validator.validate()
