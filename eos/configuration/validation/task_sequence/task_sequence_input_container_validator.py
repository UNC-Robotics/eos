from eos.configuration.entities.experiment import ExperimentConfig
from eos.configuration.entities.lab import LabConfig
from eos.configuration.entities.task import TaskConfig
from eos.configuration.exceptions import EosTaskValidationError
from eos.configuration.validation import validation_utils
from eos.configuration.validation.experiment_container_registry import ExperimentContainerRegistry
from eos.configuration.validation.task_sequence.base_task_sequence_validator import BaseTaskSequenceValidator
from eos.configuration.validation.task_sequence.task_input_container_validator import TaskInputContainerValidator


class TaskSequenceInputContainerValidator(BaseTaskSequenceValidator):
    """
    Validate the input containers of every task in a task sequence.
    """

    def __init__(
        self,
        experiment_config: ExperimentConfig,
        lab_configs: list[LabConfig],
    ):
        super().__init__(experiment_config, lab_configs)
        self._container_registry = ExperimentContainerRegistry(experiment_config, lab_configs)

    def validate(self) -> None:
        for task in self._experiment_config.tasks:
            self._validate_input_containers(task)

    def _validate_input_containers(
        self,
        task: TaskConfig,
    ) -> None:
        """
        Validate that a task gets the types and quantities of input containers it requires.
        """
        task_spec = self._tasks.get_spec_by_config(task)
        if not task.containers and task_spec.input_containers:
            raise EosTaskValidationError(f"Task '{task.id}' requires input containers but none were provided.")

        input_container_validator = TaskInputContainerValidator(task, task_spec, self._container_registry)
        input_container_validator.validate_input_containers()

        self._validate_container_references(task)

    def _validate_container_references(self, task: TaskConfig) -> None:
        for container_name, container_id in task.containers.items():
            if validation_utils.is_container_reference(container_id):
                self._validate_container_reference(container_name, container_id, task)

    def _validate_container_reference(
        self,
        container_name: str,
        container_id: str,
        task: TaskConfig,
    ) -> None:
        """
        Ensure that a container reference is valid and that it conforms to the container specification.
        """
        referenced_task_id, referenced_container = container_id.split(".")

        referenced_task = self._find_task_by_id(referenced_task_id)
        if not referenced_task:
            raise EosTaskValidationError(
                f"Container '{container_name}' in task '{task.id}' references task '{referenced_task_id}' "
                f"which does not exist."
            )

        referenced_task_spec = self._tasks.get_spec_by_config(referenced_task)

        if referenced_container not in referenced_task_spec.output_containers:
            raise EosTaskValidationError(
                f"Container '{container_name}' in task '{task.id}' references container '{referenced_container}' "
                f"which is not an output container of task '{referenced_task_id}'."
            )

        task_spec = self._tasks.get_spec_by_config(task)
        if container_name not in task_spec.input_containers:
            raise EosTaskValidationError(
                f"Container '{container_name}' is not a valid input container for task '{task.id}'."
            )

        required_container_spec = task_spec.input_containers[container_name]
        referenced_container_spec = referenced_task_spec.output_containers[referenced_container]

        if required_container_spec.type != referenced_container_spec.type:
            raise EosTaskValidationError(
                f"Type mismatch for referenced container '{referenced_container}' in task '{task.id}'. "
                f"The required container type is '{required_container_spec.type}' which does not match the referenced "
                f"container type '{referenced_container_spec.type}'."
            )

    def _find_task_by_id(self, task_id: str) -> TaskConfig | None:
        return next((task for task in self._experiment_config.tasks if task.id == task_id), None)
