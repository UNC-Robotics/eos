"""Validation coverage for `run_if` declared on protocol tasks."""

import pytest

from eos.configuration.entities.lab_def import LabDef
from eos.configuration.entities.protocol_def import ProtocolDef
from eos.configuration.entities.task_def import TaskDef
from eos.configuration.exceptions import EosTaskValidationError
from eos.configuration.protocol_graph import TaskReferenceOrderingValidator
from eos.configuration.validation import RunIfValidator
from tests.fixtures import *


LAB_NAME = "multiplication_lab"
PROTOCOL = "run_if"


def _multiplier_devices() -> dict[str, dict[str, str]]:
    return {"multiplier": {"lab_name": LAB_NAME, "name": "multiplier"}}


def _build_protocol(*tasks: TaskDef) -> ProtocolDef:
    return ProtocolDef(type="t", desc="", labs=[LAB_NAME], tasks=list(tasks))


def _multiplication(
    name: str, *, dependencies: list[str] | None = None, run_if: str | None = None, number: object = 1
) -> TaskDef:
    return TaskDef(
        name=name,
        type="Multiplication",
        devices=_multiplier_devices(),
        dependencies=dependencies or [],
        run_if=run_if,
        parameters={"number": number, "factor": 1},
    )


@pytest.mark.parametrize("setup_lab_protocol", [(LAB_NAME, PROTOCOL)], indirect=True)
class TestRunIfValidator:
    def test_sample_protocol_validates(self, setup_lab_protocol):
        # Just loading should have already run validation. Re-run RunIfValidator explicitly.
        _, protocol = setup_lab_protocol
        RunIfValidator(protocol).validate()

    def test_unknown_ref_rejected(self, setup_lab_protocol):
        protocol = _build_protocol(
            _multiplication("a"),
            _multiplication("b", dependencies=["a"], run_if="ghost.product > 0"),
        )
        with pytest.raises(EosTaskValidationError, match="references unknown task"):
            RunIfValidator(protocol).validate()

    def test_non_ancestor_ref_rejected(self, setup_lab_protocol):
        protocol = _build_protocol(
            _multiplication("a"),
            _multiplication("b"),
            _multiplication("c", dependencies=["a"], run_if="b.product > 0"),
        )
        with pytest.raises(EosTaskValidationError, match="does not run before it"):
            RunIfValidator(protocol).validate()

    def test_unknown_output_rejected(self, setup_lab_protocol):
        protocol = _build_protocol(
            _multiplication("a"),
            _multiplication("b", dependencies=["a"], run_if="a.nope > 0"),
        )
        with pytest.raises(EosTaskValidationError, match="not an output"):
            RunIfValidator(protocol).validate()

    def test_non_bool_rejected(self, setup_lab_protocol):
        protocol = _build_protocol(
            _multiplication("a"),
            _multiplication("b", dependencies=["a"], run_if="a.product"),
        )
        with pytest.raises(EosTaskValidationError, match="must evaluate to bool"):
            RunIfValidator(protocol).validate()

    def test_empty_run_if_is_ignored(self, setup_lab_protocol):
        # Empty string means "always run" (matches the executor); it must not fail to parse.
        protocol = _build_protocol(
            _multiplication("a"),
            _multiplication("b", dependencies=["a"], run_if=""),
        )
        RunIfValidator(protocol).validate()

    def test_fanin_alternate_must_be_ancestor(self, setup_lab_protocol):
        # A fan-in alternate that is not an ancestor is rejected, like a single reference.
        protocol = _build_protocol(
            _multiplication("a"),
            _multiplication("b"),
            _multiplication("c", dependencies=["a"], number=["a.product", "b.product"]),
        )
        with pytest.raises(EosTaskValidationError, match="does not run before it"):
            TaskReferenceOrderingValidator(protocol).validate()
