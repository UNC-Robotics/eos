import copy
from typing import Protocol

from eos.configuration.entities.task_def import TaskDef, DeviceAssignmentDef
from eos.configuration.utils import (
    is_device_reference,
    is_dynamic_parameter,
    is_parameter_reference,
    is_resource_reference,
)
from eos.experiments.experiment_manager import ExperimentManager
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.exceptions import EosTaskInputResolutionError
from eos.tasks.task_manager import TaskManager


class AsyncResolver(Protocol):
    async def __call__(self, db: AsyncDbSession, experiment_name: str, task: TaskDef) -> TaskDef: ...


class TaskInputResolver:
    """
    Resolves parameters, input parameter references, and input resource references for a task that is
    part of an experiment.
    """

    def __init__(self, task_manager: TaskManager, experiment_manager: ExperimentManager):
        self._task_manager = task_manager
        self._experiment_manager = experiment_manager

    async def resolve_task_inputs(self, db: AsyncDbSession, experiment_name: str, task: TaskDef) -> TaskDef:
        """
        Resolve all input references for a task.
        """
        return await self._apply_resolvers(
            db,
            experiment_name,
            task,
            [
                self._resolve_parameters,
                self._resolve_input_parameter_references,
                self._resolve_input_resource_references,
                self._resolve_input_device_references,
            ],
        )

    async def _apply_resolvers(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef, resolvers: list[AsyncResolver]
    ) -> TaskDef:
        """
        Apply a list of async resolver functions to the task config.
        """
        config = copy.deepcopy(task)
        for resolver in resolvers:
            config = await resolver(db, experiment_name, config)
        return config

    async def resolve_parameters(self, db: AsyncDbSession, experiment_name: str, task: TaskDef) -> TaskDef:
        """
        Resolve parameters for a task.
        """
        return await self._apply_resolvers(db, experiment_name, task, [self._resolve_parameters])

    async def resolve_input_parameter_references(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> TaskDef:
        """
        Resolve input parameter references for a task.
        """
        return await self._apply_resolvers(db, experiment_name, task, [self._resolve_input_parameter_references])

    async def resolve_input_resource_references(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> TaskDef:
        """
        Resolve input resource references for a task.
        """
        return await self._apply_resolvers(db, experiment_name, task, [self._resolve_input_resource_references])

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

    async def _resolve_input_parameter_references(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> TaskDef:
        for param_name, param_value in task.parameters.items():
            if not is_parameter_reference(param_value):
                continue

            ref_task_name, ref_param_name = param_value.split(".")
            resolved_value = await self._resolve_reference(
                db, experiment_name, ref_task_name, ref_param_name, "parameter"
            )

            if resolved_value is not None:
                task.parameters[param_name] = resolved_value
            else:
                raise EosTaskInputResolutionError(
                    f"Unresolved input parameter reference '{param_value}' in task '{task.name}'"
                )

        return task

    async def _resolve_input_resource_references(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> TaskDef:
        for resource_name, resource_value in task.resources.items():
            # Only strings can be references; dynamic requests remain unchanged
            if not isinstance(resource_value, str):
                continue
            if not is_resource_reference(resource_value):
                continue

            ref_task_name, ref_resource_name = resource_value.split(".")
            resolved_value = await self._resolve_reference(
                db, experiment_name, ref_task_name, ref_resource_name, "resource"
            )

            if resolved_value is not None:
                task.resources[resource_name] = resolved_value
            else:
                raise EosTaskInputResolutionError(
                    f"Unresolved input resource reference '{resource_value}' in task '{task.name}'"
                )

        return task

    async def _resolve_input_device_references(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> TaskDef:
        """
        Resolve device references (e.g., "task.device_name") to concrete TaskDeviceConfig.
        """
        for device_name, device_value in task.devices.items():
            # Only strings can be references; TaskDeviceConfig and DynamicTaskDeviceConfig remain unchanged
            if not isinstance(device_value, str):
                continue
            if not is_device_reference(device_value):
                continue

            ref_task_name, ref_device_name = device_value.split(".")
            resolved_device = await self._resolve_device_reference(db, experiment_name, ref_task_name, ref_device_name)

            if resolved_device is not None:
                task.devices[device_name] = resolved_device
            else:
                raise EosTaskInputResolutionError(
                    f"Unresolved input device reference '{device_value}' in task '{task.name}'"
                )

        return task

    async def _resolve_device_reference(
        self, db: AsyncDbSession, experiment_name: str, ref_task_name: str, ref_device_name: str
    ) -> DeviceAssignmentDef | None:
        """Look up the device allocated to a referenced task."""
        ref_task = await self._task_manager.get_task(db, experiment_name, ref_task_name)

        if ref_device_name in (ref_task.devices or {}):
            device_info = ref_task.devices[ref_device_name]
            # Devices are stored as dicts with lab_name and name after scheduling
            if isinstance(device_info, dict):
                return DeviceAssignmentDef(lab_name=device_info["lab_name"], name=device_info["name"])
            if isinstance(device_info, DeviceAssignmentDef):
                return device_info

        return None

    async def _resolve_reference(
        self, db: AsyncDbSession, experiment_name: str, ref_task_name: str, ref_name: str, ref_type: str
    ) -> str | None:
        ref_task = await self._task_manager.get_task(db, experiment_name, ref_task_name)

        if ref_type == "parameter":
            if ref_name in (ref_task.output_parameters or {}):
                return ref_task.output_parameters[ref_name]
            ref_task = await self._task_manager.get_task(db, experiment_name, ref_task_name)
            if ref_name in (ref_task.input_parameters or {}):
                return ref_task.input_parameters[ref_name]
        elif ref_type == "resource":
            if ref_name in (ref_task.output_resources or {}):
                return ref_task.output_resources[ref_name].name

        return None
