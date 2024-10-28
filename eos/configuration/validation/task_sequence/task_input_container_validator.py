from eos.configuration.entities.lab import LabContainerConfig
from eos.configuration.entities.task import TaskConfig
from eos.configuration.entities.task_spec import TaskSpecConfig, TaskSpecContainerConfig
from eos.configuration.exceptions import EosTaskValidationError
from eos.configuration.validation import validation_utils
from eos.configuration.validation.experiment_container_registry import ExperimentContainerRegistry
from eos.logging.batch_error_logger import batch_error, raise_batched_errors


class TaskInputContainerValidator:
    """
    Validates that the input containers of a task conform to the task's specification.
    """

    def __init__(
        self,
        task: TaskConfig,
        task_spec: TaskSpecConfig,
        container_registry: ExperimentContainerRegistry,
    ):
        self._task_id = task.id
        self._input_containers = task.containers
        self._task_spec = task_spec
        self._container_registry = container_registry

    def validate_input_containers(self) -> None:
        """
        Validate the input containers of a task.
        Check whether the types of containers match the task's requirements and whether the quantities are correct.
        """
        self._validate_input_container_requirements()
        raise_batched_errors(root_exception_type=EosTaskValidationError)

    def _validate_input_container_requirements(self) -> None:
        """
        Validate that the input containers of a task meet its requirements in terms of types and quantities.
        """
        required_containers = self._get_required_containers()
        provided_containers = self._get_provided_containers()

        self._validate_container_counts(required_containers, provided_containers)
        self._validate_container_types(required_containers, provided_containers)

    def _get_required_containers(self) -> dict[str, TaskSpecContainerConfig]:
        """
        Get the required containers as specified in the task specification.
        """
        return self._task_spec.input_containers

    def _get_provided_containers(self) -> dict[str, str]:
        """
        Get the provided containers, validating their existence if not a reference.
        """
        provided_containers = {}
        for container_name, container_id in self._input_containers.items():
            if validation_utils.is_container_reference(container_id):
                provided_containers[container_name] = "reference"
            else:
                lab_container = self._validate_container_exists(container_id)
                provided_containers[container_name] = lab_container.type
        return provided_containers

    def _validate_container_exists(self, container_id: str) -> LabContainerConfig:
        """
        Validate the existence of a container in the lab.
        """
        container = self._container_registry.find_container_by_id(container_id)

        if not container:
            batch_error(
                f"Container '{container_id}' in task '{self._task_id}' does not exist in the lab.",
                EosTaskValidationError,
            )

        return container

    def _validate_container_counts(
        self, required: dict[str, TaskSpecContainerConfig], provided: dict[str, str]
    ) -> None:
        """
        Validate that the total number of containers matches the requirements.
        """
        if len(provided) != len(required):
            batch_error(
                f"Task '{self._task_id}' requires {len(required)} container(s) but {len(provided)} were provided.",
                EosTaskValidationError,
            )

    def _validate_container_types(self, required: dict[str, TaskSpecContainerConfig], provided: dict[str, str]) -> None:
        """
        Validate that the types of non-reference containers match the requirements.
        """
        for container_name, container_spec in required.items():
            if container_name not in provided:
                batch_error(
                    f"Required container '{container_name}' not provided for task '{self._task_id}'.",
                    EosTaskValidationError,
                )
            elif provided[container_name] != "reference" and provided[container_name] != container_spec.type:
                batch_error(
                    f"Container '{container_name}' in task '{self._task_id}' has incorrect type. "
                    f"Expected '{container_spec.type}' but got '{provided[container_name]}'.",
                    EosTaskValidationError,
                )

        for container_name in provided:
            if container_name not in required:
                batch_error(
                    f"Unexpected container '{container_name}' provided for task '{self._task_id}'.",
                    EosTaskValidationError,
                )
