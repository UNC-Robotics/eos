from typing import Any

from eos.configuration.entities.task_parameters import TaskParameterType
from eos.configuration.exceptions import EosTaskValidationError
from eos.configuration.registries import TaskSpecRegistry
from eos.tasks.entities.task import TaskSubmission


class TaskInputParameterCaster:
    def __init__(self):
        self.task_spec_registry = TaskSpecRegistry()

    def cast_input_parameters(self, task_submission: TaskSubmission) -> dict[str, Any]:
        """
        Cast input parameters of a task to the expected Python types.

        :param task_submission: The task submission.
        :return: The input parameters cast to the expected Python types.
        """
        task_name = task_submission.name
        task_type = task_submission.type
        input_parameters = task_submission.input_parameters

        task_spec = self.task_spec_registry.get_spec_by_type(task_type)

        for parameter_name, parameter in input_parameters.items():
            try:
                parameter_type = TaskParameterType(task_spec.input_parameters[parameter_name].type)
                input_parameters[parameter_name] = parameter_type.python_type(parameter)
            except TypeError as e:
                raise EosTaskValidationError(
                    f"Failed to cast input parameter '{parameter_name}' of task '{task_name}' of type \
                    f'{type(parameter)}' to the expected type '{task_spec.input_parameters[parameter_name].type}'."
                ) from e

        return input_parameters
