from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.logging.batch_error_logger import batch_error, raise_batched_errors
from eos.tasks.exceptions import EosTaskValidationError


class TaskInputFileValidator:
    """Validates that a task provides the input files required by its specification."""

    def __init__(self, task: TaskDef, task_spec: TaskSpecDef):
        self._task_name = task.name
        self._input_files = task.files
        self._required_files = task_spec.input_files or {}

    def validate(self) -> None:
        """Ensure every required input file slot is provided and no unknown slots are present."""
        if not self._required_files and not self._input_files:
            return

        for input_name in self._input_files:
            if input_name not in self._required_files:
                batch_error(
                    f"Input file '{input_name}' is not a valid input file for task '{self._task_name}'.",
                    EosTaskValidationError,
                )
        for input_name in self._required_files:
            value = self._input_files.get(input_name)
            if not value or not str(value).strip():
                batch_error(
                    f"Required input file '{input_name}' not provided for task '{self._task_name}'.",
                    EosTaskValidationError,
                )
        raise_batched_errors(root_exception_type=EosTaskValidationError)
