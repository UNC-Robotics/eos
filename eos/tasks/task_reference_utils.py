"""Shared helpers for resolving `task.output` references across the system."""

from typing import Any, TYPE_CHECKING

from eos.configuration.entities.task_def import DeviceAssignmentDef
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import Task

if TYPE_CHECKING:
    from eos.tasks.task_manager import TaskManager


async def fetch_ref_tasks(
    task_manager: "TaskManager",
    db: AsyncDbSession,
    protocol_run_name: str,
    ref_names: set[str],
) -> dict[str, Task]:
    """Fetch the named tasks for a protocol run; returns a name->Task map."""
    if not ref_names:
        return {}
    lookup = await task_manager.get_tasks_by_protocol_runs(db, [protocol_run_name], list(ref_names))
    return {task_name: t for (_, task_name), t in lookup.items()}


def resolve_parameter(ref_tasks: dict[str, Task], task_name: str, output_name: str) -> Any | None:
    """Look up an output (or input) parameter value on a referenced task."""
    ref_task = ref_tasks.get(task_name)
    if ref_task is None:
        return None
    if output_name in (ref_task.output_parameters or {}):
        return ref_task.output_parameters[output_name]
    if output_name in (ref_task.input_parameters or {}):
        return ref_task.input_parameters[output_name]
    return None


def resolve_resource(ref_tasks: dict[str, Task], task_name: str, output_name: str) -> str | None:
    """Look up an output resource's name on a referenced task."""
    ref_task = ref_tasks.get(task_name)
    if ref_task is None:
        return None
    if output_name in (ref_task.output_resources or {}):
        return ref_task.output_resources[output_name].name
    return None


def resolve_device(ref_tasks: dict[str, Task], task_name: str, device_name: str) -> DeviceAssignmentDef | None:
    """Look up a referenced task's device assignment."""
    ref_task = ref_tasks.get(task_name)
    if ref_task is None:
        return None
    if device_name not in (ref_task.devices or {}):
        return None
    device_info = ref_task.devices[device_name]
    if isinstance(device_info, dict):
        return DeviceAssignmentDef(lab_name=device_info["lab_name"], name=device_info["name"])
    if isinstance(device_info, DeviceAssignmentDef):
        return device_info
    return None
