from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.tasks.validation.task_device_validator import TaskDeviceValidator
from eos.tasks.validation.task_input_file_validator import TaskInputFileValidator
from eos.tasks.validation.task_input_parameter_validator import TaskInputParameterValidator


class TaskValidator:
    def __init__(self, configuration_manager: ConfigurationManager):
        self.configuration_manager = configuration_manager
        self.task_specs = configuration_manager.task_specs

    def validate(self, task: TaskDef) -> None:
        task_spec = self.task_specs.get_spec_by_type(task.type)
        self._validate_devices(task, task_spec)
        self._validate_resources(task, task_spec)
        self._validate_parameters(task, task_spec)
        self._validate_files(task, task_spec)

    def _validate_devices(self, task: TaskDef, task_spec: TaskSpecDef) -> None:
        validator = TaskDeviceValidator(task, task_spec, self.configuration_manager)
        validator.validate()

    def _validate_parameters(self, task: TaskDef, task_spec: TaskSpecDef) -> None:
        validator = TaskInputParameterValidator(task, task_spec)
        validator.validate()

    def _validate_resources(self, task: TaskDef, task_spec: TaskSpecDef) -> None:
        declared = task_spec.input_resources
        unexpected = task.resources.keys() - declared.keys()
        if unexpected:
            raise ValueError(f"Task '{task.name}' has undeclared resources: {sorted(unexpected)}")

        required = {name for name, spec in declared.items() if not spec.optional}
        missing = required - task.resources.keys()
        if missing:
            raise ValueError(f"Task '{task.name}' is missing required resources: {sorted(missing)}")

    def _validate_files(self, task: TaskDef, task_spec: TaskSpecDef) -> None:
        validator = TaskInputFileValidator(task, task_spec)
        validator.validate()
