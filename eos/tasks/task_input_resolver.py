import copy

from eos.configuration.entities.task_def import TaskDef, DeviceAssignmentDef
from eos.configuration.utils import (
    is_device_reference,
    is_dynamic_parameter,
    is_parameter_reference,
    is_resource_reference,
)
from eos.experiments.experiment_manager import ExperimentManager
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import Task
from eos.tasks.exceptions import EosTaskInputResolutionError
from eos.tasks.task_manager import TaskManager


class TaskInputResolver:
    """
    Resolves parameters, input parameter references, and input resource references for a task that is
    part of an experiment.
    """

    def __init__(self, task_manager: TaskManager, experiment_manager: ExperimentManager):
        self._task_manager = task_manager
        self._experiment_manager = experiment_manager

    async def resolve_task_inputs(self, db: AsyncDbSession, experiment_name: str, task: TaskDef) -> TaskDef:
        config = copy.deepcopy(task)
        config = await self._resolve_parameters(db, experiment_name, config)

        ref_tasks = await self._fetch_ref_tasks(db, experiment_name, config)
        self._apply_parameter_references(ref_tasks, config)
        self._apply_resource_references(ref_tasks, config)
        self._apply_device_references(ref_tasks, config)

        return config

    async def resolve_parameters(self, db: AsyncDbSession, experiment_name: str, task: TaskDef) -> TaskDef:
        config = copy.deepcopy(task)
        return await self._resolve_parameters(db, experiment_name, config)

    async def resolve_input_parameter_references(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> TaskDef:
        config = copy.deepcopy(task)
        ref_tasks = await self._fetch_ref_tasks(db, experiment_name, config)
        self._apply_parameter_references(ref_tasks, config)
        return config

    async def resolve_input_resource_references(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> TaskDef:
        config = copy.deepcopy(task)
        ref_tasks = await self._fetch_ref_tasks(db, experiment_name, config)
        self._apply_resource_references(ref_tasks, config)
        return config

    async def _fetch_ref_tasks(self, db: AsyncDbSession, experiment_name: str, task: TaskDef) -> dict[str, Task]:
        ref_names = self._collect_referenced_task_names(task)
        if not ref_names:
            return {}
        task_lookup = await self._task_manager.get_tasks_by_experiments(db, [experiment_name], list(ref_names))
        return {task_name: t for (_, task_name), t in task_lookup.items()}

    @staticmethod
    def _collect_referenced_task_names(task: TaskDef) -> set[str]:
        ref_names: set[str] = set()
        for param_value in task.parameters.values():
            if is_parameter_reference(param_value):
                ref_names.add(param_value.split(".")[0])
        for resource_value in task.resources.values():
            if isinstance(resource_value, str) and is_resource_reference(resource_value):
                ref_names.add(resource_value.split(".")[0])
        for device_value in task.devices.values():
            if isinstance(device_value, str) and is_device_reference(device_value):
                ref_names.add(device_value.split(".")[0])
        return ref_names

    async def _resolve_parameters(self, db: AsyncDbSession, experiment_name: str, task: TaskDef) -> TaskDef:
        experiment = await self._experiment_manager.get_experiment(db, experiment_name)
        task_parameters = experiment.parameters.get(task.name, {})

        task.parameters.update(task_parameters)

        unresolved_parameters = [param for param, value in task.parameters.items() if is_dynamic_parameter(value)]

        if unresolved_parameters:
            raise EosTaskInputResolutionError(
                f"Unresolved input parameters in task '{task.name}': {unresolved_parameters}"
            )

        return task

    @staticmethod
    def _resolve_reference(ref_tasks: dict[str, Task], ref_task_name: str, ref_name: str, ref_type: str) -> str | None:
        ref_task = ref_tasks.get(ref_task_name)
        if ref_task is None:
            return None

        if ref_type == "parameter":
            if ref_name in (ref_task.output_parameters or {}):
                return ref_task.output_parameters[ref_name]
            if ref_name in (ref_task.input_parameters or {}):
                return ref_task.input_parameters[ref_name]
        elif ref_type == "resource":
            if ref_name in (ref_task.output_resources or {}):
                return ref_task.output_resources[ref_name].name

        return None

    @staticmethod
    def _resolve_device_reference(
        ref_tasks: dict[str, Task], ref_task_name: str, ref_device_name: str
    ) -> DeviceAssignmentDef | None:
        ref_task = ref_tasks.get(ref_task_name)
        if ref_task is None:
            return None

        if ref_device_name in (ref_task.devices or {}):
            device_info = ref_task.devices[ref_device_name]
            if isinstance(device_info, dict):
                return DeviceAssignmentDef(lab_name=device_info["lab_name"], name=device_info["name"])
            if isinstance(device_info, DeviceAssignmentDef):
                return device_info

        return None

    @staticmethod
    def _apply_parameter_references(ref_tasks: dict[str, Task], task: TaskDef) -> None:
        for param_name, param_value in task.parameters.items():
            if not is_parameter_reference(param_value):
                continue

            ref_task_name, ref_param_name = param_value.split(".")
            resolved_value = TaskInputResolver._resolve_reference(ref_tasks, ref_task_name, ref_param_name, "parameter")

            if resolved_value is not None:
                task.parameters[param_name] = resolved_value
            else:
                raise EosTaskInputResolutionError(
                    f"Unresolved input parameter reference '{param_value}' in task '{task.name}'"
                )

    @staticmethod
    def _apply_resource_references(ref_tasks: dict[str, Task], task: TaskDef) -> None:
        for resource_name, resource_value in task.resources.items():
            if not isinstance(resource_value, str):
                continue
            if not is_resource_reference(resource_value):
                continue

            ref_task_name, ref_resource_name = resource_value.split(".")
            resolved_value = TaskInputResolver._resolve_reference(
                ref_tasks, ref_task_name, ref_resource_name, "resource"
            )

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
            resolved_device = TaskInputResolver._resolve_device_reference(ref_tasks, ref_task_name, ref_device_name)

            if resolved_device is not None:
                task.devices[device_name] = resolved_device
            else:
                raise EosTaskInputResolutionError(
                    f"Unresolved input device reference '{device_value}' in task '{task.name}'"
                )
