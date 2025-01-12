from typing import Any

from eos.configuration.entities.task_parameters import TaskParameterType
from eos.configuration.exceptions import EosTaskValidationError
from eos.configuration.spec_registries.task_spec_registry import TaskSpecRegistry
from eos.tasks.entities.task import TaskDefinition


class TaskInputParameterCaster:
    def __init__(self):
        self.task_spec_registry = TaskSpecRegistry()

    def cast_input_parameters(self, task_definition: TaskDefinition) -> dict[str, Any]:
        """
        Cast input parameters of a task to the expected Python types.

        :param task_definition: The task definition.
        :return: The input parameters cast to the expected Python types.
        """
        task_id = task_definition.id
        task_type = task_definition.type
        input_parameters = task_definition.input_parameters

        task_spec = self.task_spec_registry.get_spec_by_type(task_type)

        for parameter_name, parameter in input_parameters.items():
            try:
                parameter_type = TaskParameterType(task_spec.input_parameters[parameter_name].type)
                input_parameters[parameter_name] = parameter_type.python_type(parameter)
            except TypeError as e:
                raise EosTaskValidationError(
                    f"Failed to cast input parameter '{parameter_name}' of task '{task_id}' of type \
                    f'{type(parameter)}' to the expected type '{task_spec.input_parameters[parameter_name].type}'."
                ) from e

        return input_parameters
