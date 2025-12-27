from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.tasks.validation.task_device_validator import TaskDeviceValidator
from eos.tasks.validation.task_input_parameter_validator import TaskInputParameterValidator


class TaskValidator:
    def __init__(self, configuration_manager: ConfigurationManager):
        self.configuration_manager = configuration_manager
        self.task_specs = configuration_manager.task_specs

    def validate(self, task: TaskDef) -> None:
        task_spec = self.task_specs.get_spec_by_type(task.type)
        self._validate_devices(task, task_spec)
        self._validate_parameters(task, task_spec)

    def _validate_devices(self, task: TaskDef, task_spec: TaskSpecDef) -> None:
        validator = TaskDeviceValidator(task, task_spec, self.configuration_manager)
        validator.validate()

    def _validate_parameters(self, task: TaskDef, task_spec: TaskSpecDef) -> None:
        validator = TaskInputParameterValidator(task, task_spec)
        validator.validate()
