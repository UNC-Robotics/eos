import copy
from typing import Any

from eos.configuration.entities.task_def import TaskDef
from eos.configuration.registries import TaskSpecRegistry
from eos.configuration.utils import (
    is_device_reference,
    is_dynamic_parameter,
    is_fanin_parameter,
    is_parameter_reference,
    is_resource_reference,
)
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import Task, TaskStatus
from eos.tasks.exceptions import EosTaskInputResolutionError
from eos.tasks.task_manager import TaskManager
from eos.tasks.task_reference_utils import (
    fetch_ref_tasks,
    resolve_device,
    resolve_parameter,
    resolve_resource,
)


class TaskInputResolver:
    """Resolve parameter, resource, and device references for a task in a protocol run."""

    def __init__(self, task_manager: TaskManager, protocol_run_manager: ProtocolRunManager):
        self._task_manager = task_manager
        self._protocol_run_manager = protocol_run_manager
        self._task_spec_registry = TaskSpecRegistry()

    async def resolve_task_inputs(self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef) -> TaskDef:
        config = copy.deepcopy(task)
        config = await self._resolve_parameters(db, protocol_run_name, config)

        ref_tasks = await self._fetch_ref_tasks(db, protocol_run_name, config)
        self._apply_parameter_references(ref_tasks, config)
        self._apply_resource_references(ref_tasks, config)
        self._apply_device_references(ref_tasks, config)

        return config

    async def resolve_parameters(self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef) -> TaskDef:
        config = copy.deepcopy(task)
        return await self._resolve_parameters(db, protocol_run_name, config)

    async def resolve_input_parameter_references(
        self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef
    ) -> TaskDef:
        config = copy.deepcopy(task)
        ref_tasks = await self._fetch_ref_tasks(db, protocol_run_name, config)
        self._apply_parameter_references(ref_tasks, config)
        return config

    async def resolve_input_resource_references(
        self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef
    ) -> TaskDef:
        config = copy.deepcopy(task)
        ref_tasks = await self._fetch_ref_tasks(db, protocol_run_name, config)
        self._apply_resource_references(ref_tasks, config)
        return config

    async def _fetch_ref_tasks(self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef) -> dict[str, Task]:
        return await fetch_ref_tasks(
            self._task_manager, db, protocol_run_name, self._collect_referenced_task_names(task)
        )

    @staticmethod
    def _collect_referenced_task_names(task: TaskDef) -> set[str]:
        ref_names: set[str] = set()
        for param_value in task.parameters.values():
            if is_parameter_reference(param_value):
                ref_names.add(param_value.split(".")[0])
            elif is_fanin_parameter(param_value):
                for alt in param_value:
                    ref_names.add(alt.split(".")[0])
        for resource_value in task.resources.values():
            if isinstance(resource_value, str) and is_resource_reference(resource_value):
                ref_names.add(resource_value.split(".")[0])
        for device_value in task.devices.values():
            if isinstance(device_value, str) and is_device_reference(device_value):
                ref_names.add(device_value.split(".")[0])
        return ref_names

    async def _resolve_parameters(self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef) -> TaskDef:
        protocol_run = await self._protocol_run_manager.get_protocol_run(db, protocol_run_name)
        task_parameters = protocol_run.parameters.get(task.name, {})

        # Fill task.yml defaults for params not set by protocol.yml or the run submission
        task_spec = self._task_spec_registry.get_spec_by_type(task.type)
        if task_spec is not None:
            for param_name, param_spec in task_spec.iter_parameters():
                if param_name in task.parameters or param_name in task_parameters:
                    continue
                if param_spec.value is None:
                    continue
                task.parameters[param_name] = param_spec.value

        task.parameters.update(task_parameters)

        unresolved_parameters = [param for param, value in task.parameters.items() if is_dynamic_parameter(value)]

        if unresolved_parameters:
            raise EosTaskInputResolutionError(
                f"Unresolved input parameters in task '{task.name}': {unresolved_parameters}"
            )

        return task

    @staticmethod
    def _apply_parameter_references(ref_tasks: dict[str, Task], task: TaskDef) -> None:
        for param_name, param_value in task.parameters.items():
            if is_parameter_reference(param_value):
                ref_task_name, ref_param_name = param_value.split(".")
                resolved_value = resolve_parameter(ref_tasks, ref_task_name, ref_param_name)
                if resolved_value is None:
                    raise EosTaskInputResolutionError(
                        f"Unresolved input parameter reference '{param_value}' in task '{task.name}'"
                    )
                task.parameters[param_name] = resolved_value
            elif is_fanin_parameter(param_value):
                task.parameters[param_name] = TaskInputResolver._resolve_fanin(
                    ref_tasks, param_value, task.name, param_name
                )

    @staticmethod
    def _resolve_fanin(ref_tasks: dict[str, Task], alternates: list[str], task_name: str, param_name: str) -> Any:
        # A branch is live if its source task COMPLETED; a legitimately None-valued output still counts.
        live = []
        for ref in alternates:
            ref_task_name, ref_output = ref.split(".")
            ref_task = ref_tasks.get(ref_task_name)
            if ref_task is not None and ref_task.status == TaskStatus.COMPLETED:
                live.append((ref, resolve_parameter(ref_tasks, ref_task_name, ref_output)))
        if not live:
            raise EosTaskInputResolutionError(
                f"Fan-in parameter '{param_name}' in task '{task_name}' has no completed source "
                f"(all alternates skipped or missing): {alternates}"
            )
        if len(live) > 1:
            refs = [r for r, _ in live]
            raise EosTaskInputResolutionError(
                f"Fan-in parameter '{param_name}' in task '{task_name}' has multiple completed sources; "
                f"branch run_if conditions must be mutually exclusive so exactly one runs: {refs}"
            )
        return live[0][1]

    @staticmethod
    def _apply_resource_references(ref_tasks: dict[str, Task], task: TaskDef) -> None:
        for resource_name, resource_value in task.resources.items():
            if not isinstance(resource_value, str):
                continue
            if not is_resource_reference(resource_value):
                continue

            ref_task_name, ref_resource_name = resource_value.split(".")
            resolved_value = resolve_resource(ref_tasks, ref_task_name, ref_resource_name)

            if resolved_value is not None:
                task.resources[resource_name] = resolved_value
            else:
                raise EosTaskInputResolutionError(
                    f"Unresolved input resource reference '{resource_value}' in task '{task.name}'"
                )

    @staticmethod
    def _apply_device_references(ref_tasks: dict[str, Task], task: TaskDef) -> None:
        for device_name, device_value in task.devices.items():
            if not isinstance(device_value, str):
                continue
            if not is_device_reference(device_value):
                continue

            ref_task_name, ref_device_name = device_value.split(".")
            resolved_device = resolve_device(ref_tasks, ref_task_name, ref_device_name)

            if resolved_device is not None:
                task.devices[device_name] = resolved_device
            else:
                raise EosTaskInputResolutionError(
                    f"Unresolved input device reference '{device_value}' in task '{task.name}'"
                )
