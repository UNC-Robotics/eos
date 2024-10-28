from eos.configuration.entities.task_parameters import (
    TaskParameterType,
)
from eos.configuration.entities.task import TaskConfig
from eos.configuration.exceptions import (
    EosTaskValidationError,
)
from eos.configuration.validation import validation_utils
from eos.configuration.validation.task_sequence.base_task_sequence_validator import (
    BaseTaskSequenceValidator,
)
from eos.configuration.validation.task_sequence.task_input_parameter_validator import (
    TaskInputParameterValidator,
)


class TaskSequenceInputParameterValidator(BaseTaskSequenceValidator):
    """
    Validate the input parameters of every task in a task sequence.
    """

    def validate(self) -> None:
        for task in self._experiment_config.tasks:
            self._validate_input_parameters(task)

    def _validate_input_parameters(self, task: TaskConfig) -> None:
        task_spec = self._tasks.get_spec_by_config(task)

        if task_spec.input_parameters is None and task.parameters is not None:
            raise EosTaskValidationError(
                f"Task '{task.id}' does not accept input parameters but parameters were provided."
            )

        parameter_validator = TaskInputParameterValidator(task, task_spec)
        parameter_validator.validate_input_parameters()

        self._validate_parameter_references(task)

    def _validate_parameter_references(self, task: TaskConfig) -> None:
        for parameter_name, parameter in task.parameters.items():
            if validation_utils.is_parameter_reference(parameter):
                self._validate_parameter_reference(parameter_name, task)

    def _validate_parameter_reference(
        self,
        parameter_name: str,
        task: TaskConfig,
    ) -> None:
        """
        Ensure that a parameter reference is valid and that it conforms to the parameter specification.
        """
        parameter = task.parameters[parameter_name]
        referenced_task_id, referenced_parameter = str(parameter).split(".")

        referenced_task = self._find_task_by_id(referenced_task_id)
        if not referenced_task:
            raise EosTaskValidationError(
                f"Parameter '{parameter_name}' in task '{task.id}' references task '{referenced_task_id}' "
                f"which does not exist."
            )

        referenced_task_spec = self._tasks.get_spec_by_config(referenced_task)

        referenced_parameter_spec = None
        if (
            referenced_task_spec.output_parameters
            and referenced_task_spec.output_parameters
            and referenced_parameter in referenced_task_spec.output_parameters
        ):
            referenced_parameter_spec = referenced_task_spec.output_parameters[referenced_parameter]
        elif (
            referenced_task_spec.input_parameters
            and referenced_task_spec.input_parameters
            and referenced_parameter in referenced_task_spec.input_parameters
        ):
            referenced_parameter_spec = referenced_task_spec.input_parameters[referenced_parameter]

        if not referenced_parameter_spec:
            raise EosTaskValidationError(
                f"Parameter '{parameter_name}' in task '{task.id}' references parameter '{referenced_parameter}' "
                f"which does not exist in task '{referenced_task_id}'."
            )

        task_spec = self._tasks.get_spec_by_config(task)
        parameter_spec = task_spec.input_parameters[parameter_name]

        if (
            TaskParameterType(parameter_spec.type).python_type
            != TaskParameterType(referenced_parameter_spec.type).python_type
        ):
            raise EosTaskValidationError(
                f"Type mismatch for referenced parameter '{referenced_parameter}' in task '{task.id}'. "
                f"The required parameter type is '{parameter_spec.type}' which does not match the referenced parameter "
                f"type '{referenced_parameter_spec.type.value}'."
            )
