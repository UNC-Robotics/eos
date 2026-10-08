from unittest.mock import AsyncMock, Mock, patch

import pytest

from eos.configuration.entities.lab_def import LabDef
from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.configuration.exceptions import EosTaskValidationError
from eos.configuration.validation import TaskValidator as ProtocolTaskValidator
from eos.orchestration.services.task_service import TaskService
from eos.resources.entities.resource import Resource
from eos.tasks.entities.task import TaskSubmission
from eos.tasks.validation.task_device_validator import TaskDeviceValidator
from eos.tasks.validation.task_validator import TaskValidator


@pytest.fixture(autouse=True)
def isolated_spec_registry():
    with patch("eos.configuration.validation.TaskSpecRegistry"):
        yield


@pytest.mark.parametrize(
    "assignment",
    [
        {"lab_name": "lab", "name": "heater"},
        {"allocation_type": "dynamic", "device_type": "heater"},
        "previous.heater",
    ],
)
@pytest.mark.parametrize("declared", [{}, {"arm": {"type": "arm", "optional": True}}])
def test_undeclared_devices_rejected_at_load_and_execution(assignment, declared):
    spec = TaskSpecDef(type="Task", devices=declared)
    task = TaskDef(name="task", type="Task", devices={"extra": assignment})

    with pytest.raises(EosTaskValidationError, match="Unexpected device 'extra'"):
        ProtocolTaskValidator(Mock(), [])._validate_task_devices(task, spec)

    with pytest.raises(ValueError, match="undeclared devices"):
        TaskDeviceValidator(task, spec, Mock()).validate()


@pytest.mark.parametrize("include_optional", [False, True])
def test_declared_optional_devices_can_be_omitted_or_supplied(include_optional):
    spec = TaskSpecDef(type="Task", devices={"heater": {"type": "heater", "optional": True}})
    devices = {"heater": {"allocation_type": "dynamic", "device_type": "heater"}} if include_optional else {}
    task = TaskDef(name="task", type="Task", devices=devices)
    lab = LabDef(name="lab", desc="Test lab", devices={"heater": {"type": "heater", "computer": "eos_computer"}})

    ProtocolTaskValidator(Mock(labs=["lab"]), [lab])._validate_task_devices(task, spec)
    TaskDeviceValidator(task, spec, Mock()).validate()


def test_optional_devices_still_require_the_declared_type():
    spec = TaskSpecDef(type="Task", devices={"heater": {"type": "heater", "optional": True}})
    task = TaskDef(name="task", type="Task", devices={"heater": {"device_type": "arm"}})

    with pytest.raises(ValueError, match="requires type 'heater'"):
        TaskDeviceValidator(task, spec, Mock()).validate()


def test_required_devices_cannot_be_omitted():
    spec = TaskSpecDef(type="Task", devices={"heater": {"type": "heater"}})
    task = TaskDef(name="task", type="Task")

    with pytest.raises(EosTaskValidationError, match="Required device 'heater'"):
        ProtocolTaskValidator(Mock(), [])._validate_task_devices(task, spec)
    with pytest.raises(ValueError, match="missing required devices"):
        TaskDeviceValidator(task, spec, Mock()).validate()


@pytest.mark.parametrize("declared", [{}, {"beaker": {"type": "beaker", "optional": True}}])
def test_undeclared_resources_rejected_at_load_and_execution(declared):
    spec = TaskSpecDef(type="Task", input_resources=declared)
    task = TaskDef(name="task", type="Task", resources={"extra": {"resource_type": "beaker"}})

    with pytest.raises(EosTaskValidationError, match="Unexpected resource 'extra'"):
        ProtocolTaskValidator(Mock(), [])._validate_task_resources(task, spec)
    with pytest.raises(ValueError, match="undeclared resources"):
        TaskValidator(Mock())._validate_resources(task, spec)


def test_runtime_resources_distinguish_required_and_optional():
    spec = TaskSpecDef(
        type="Task", input_resources={"beaker": {"type": "beaker"}, "slot": {"type": "slot", "optional": True}}
    )
    validator = TaskValidator(Mock())
    validator._validate_resources(TaskDef(name="task", type="Task", resources={"beaker": "beaker_1"}), spec)

    with pytest.raises(ValueError, match="missing required resources"):
        validator._validate_resources(TaskDef(name="task", type="Task", resources={"slot": "slot_1"}), spec)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["device", "resource"])
async def test_on_demand_submission_rejects_extras_before_scheduling(kind):
    config = Mock()
    config.task_specs.get_spec_by_type.return_value = TaskSpecDef(type="Task")
    scheduler = AsyncMock()
    service = TaskService(config, AsyncMock(), Mock(), scheduler, Mock())
    submission = TaskSubmission(name="task", type="Task")
    if kind == "device":
        submission = TaskSubmission(name="task", type="Task", devices={"extra": {"lab_name": "lab", "name": "heater"}})
    else:
        submission.input_resources = {"extra": Resource(name="beaker_1", type="beaker")}

    with pytest.raises(ValueError, match="undeclared"):
        await service.submit_task(Mock(), submission)
    scheduler.submit_on_demand_task.assert_not_called()
