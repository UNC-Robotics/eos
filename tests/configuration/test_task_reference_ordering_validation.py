import pytest

from eos.configuration.entities.protocol_def import ProtocolDef
from eos.configuration.entities.task_def import TaskDef
from eos.configuration.exceptions import EosTaskGraphError, EosTaskValidationError
from eos.configuration.protocol_graph import TaskReferenceOrderingValidator


def _protocol(tasks: list[TaskDef]) -> ProtocolDef:
    return ProtocolDef(type="test_protocol", desc="test", labs=["test_lab"], tasks=tasks)


def _task(
    name: str,
    *,
    dependencies: list[str] | None = None,
    parameters: dict | None = None,
    resources: dict | None = None,
    devices: dict | None = None,
    files: dict | None = None,
) -> TaskDef:
    return TaskDef(
        name=name,
        type="T",
        dependencies=dependencies or [],
        parameters=parameters or {},
        resources=resources or {},
        devices=devices or {},
        files=files or {},
    )


class TestTaskReferenceOrderingValidator:
    def test_direct_ancestor_reference_passes(self):
        protocol = _protocol(
            [
                _task("a"),
                _task("b", dependencies=["a"], parameters={"x": "a.out"}),
            ]
        )
        TaskReferenceOrderingValidator(protocol).validate()

    def test_transitive_ancestor_reference_passes(self):
        protocol = _protocol(
            [
                _task("a"),
                _task("b", dependencies=["a"]),
                _task("c", dependencies=["b"], parameters={"x": "a.out"}),
            ]
        )
        TaskReferenceOrderingValidator(protocol).validate()

    def test_concurrent_reference_fails(self):
        protocol = _protocol(
            [
                _task("root"),
                _task("a", dependencies=["root"]),
                _task("b", dependencies=["root"], parameters={"x": "a.out"}),
            ]
        )
        with pytest.raises(EosTaskValidationError, match="does not run before"):
            TaskReferenceOrderingValidator(protocol).validate()

    def test_downstream_reference_fails(self):
        protocol = _protocol(
            [
                _task("b", parameters={"x": "a.out"}),
                _task("a", dependencies=["b"]),
            ]
        )
        with pytest.raises(EosTaskValidationError, match="does not run before"):
            TaskReferenceOrderingValidator(protocol).validate()

    def test_self_reference_fails(self):
        protocol = _protocol([_task("a", parameters={"x": "a.y"})])
        with pytest.raises(EosTaskValidationError, match="references itself"):
            TaskReferenceOrderingValidator(protocol).validate()

    def test_dependency_cycle_raises_graph_error(self):
        protocol = _protocol(
            [
                _task("a", dependencies=["b"]),
                _task("b", dependencies=["a"]),
            ]
        )
        with pytest.raises(EosTaskGraphError, match="cycles"):
            TaskReferenceOrderingValidator(protocol)

    def test_resource_reference_ordering(self):
        protocol = _protocol(
            [
                _task("root"),
                _task("a", dependencies=["root"]),
                _task("b", dependencies=["root"], resources={"beaker": "a.beaker"}),
            ]
        )
        with pytest.raises(EosTaskValidationError, match="resource 'beaker'"):
            TaskReferenceOrderingValidator(protocol).validate()

    def test_device_reference_ordering(self):
        protocol = _protocol(
            [
                _task("root"),
                _task("a", dependencies=["root"]),
                _task("b", dependencies=["root"], devices={"arm": "a.arm"}),
            ]
        )
        with pytest.raises(EosTaskValidationError, match="device 'arm'"):
            TaskReferenceOrderingValidator(protocol).validate()

    def test_file_reference_ancestor_passes(self):
        protocol = _protocol(
            [
                _task("a"),
                _task("b", dependencies=["a"], files={"input": "a.out.txt"}),
            ]
        )
        TaskReferenceOrderingValidator(protocol).validate()

    def test_file_reference_concurrent_fails(self):
        protocol = _protocol(
            [
                _task("root"),
                _task("a", dependencies=["root"]),
                _task("b", dependencies=["root"], files={"input": "a.out.txt"}),
            ]
        )
        with pytest.raises(EosTaskValidationError, match="file 'input'"):
            TaskReferenceOrderingValidator(protocol).validate()

    def test_file_self_reference_fails(self):
        protocol = _protocol([_task("a", files={"input": "a.out.txt"})])
        with pytest.raises(EosTaskValidationError, match="references itself"):
            TaskReferenceOrderingValidator(protocol).validate()

    def test_batched_errors_report_all_violations(self):
        protocol = _protocol(
            [
                _task("root"),
                _task("a", dependencies=["root"]),
                _task(
                    "b",
                    dependencies=["root"],
                    parameters={"x": "a.out"},
                    resources={"beaker": "a.beaker"},
                ),
            ]
        )
        with pytest.raises(EosTaskValidationError) as exc_info:
            TaskReferenceOrderingValidator(protocol).validate()
        message = str(exc_info.value)
        assert "parameter 'x'" in message
        assert "resource 'beaker'" in message

    def test_dangling_reference_is_silently_skipped(self):
        protocol = _protocol(
            [
                _task("a", parameters={"x": "ghost.out"}),
            ]
        )
        # Dangling references are reported by TaskValidator, not this validator.
        TaskReferenceOrderingValidator(protocol).validate()
