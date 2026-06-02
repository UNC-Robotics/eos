import pytest

from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.tasks.exceptions import EosTaskValidationError
from eos.tasks.validation.task_input_file_validator import TaskInputFileValidator


class TestTaskInputFileValidator:
    @pytest.fixture
    def task_spec(self):
        return TaskSpecDef(
            type="test_task",
            desc="A test task",
            input_files={"input": {"desc": "The file to read."}},
        )

    @staticmethod
    def _validator(files: dict[str, str], task_spec: TaskSpecDef) -> TaskInputFileValidator:
        return TaskInputFileValidator(TaskDef(name="t1", type="test_task", files=files), task_spec)

    def test_required_file_provided_passes(self, task_spec):
        self._validator({"input": "run/gen/file.txt"}, task_spec).validate()

    def test_missing_required_file_fails(self, task_spec):
        with pytest.raises(EosTaskValidationError, match="Required input file 'input'"):
            self._validator({}, task_spec).validate()

    def test_blank_required_file_value_fails(self, task_spec):
        with pytest.raises(EosTaskValidationError, match="Required input file 'input'"):
            self._validator({"input": "   "}, task_spec).validate()

    def test_unknown_file_slot_fails(self, task_spec):
        with pytest.raises(EosTaskValidationError, match="not a valid input file"):
            self._validator({"input": "run/gen/file.txt", "bogus": "run/gen/x.txt"}, task_spec).validate()

    def test_no_files_required_and_none_provided_passes(self):
        self._validator({}, TaskSpecDef(type="test_task", desc="no files")).validate()
