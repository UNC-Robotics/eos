import asyncio
from dataclasses import dataclass
from typing import Any

import ray
from omegaconf import OmegaConf
from ray import ObjectRef

from eos.configuration.configuration_manager import ConfigurationManager
from eos.containers.container_manager import ContainerManager
from eos.containers.entities.container import Container
from eos.devices.device_actor_wrapper_registry import DeviceActorReference, DeviceActorWrapperRegistry
from eos.devices.device_manager import DeviceManager
from eos.logging.logger import log
from eos.resource_allocation.entities.resource_request import (
    ActiveResourceAllocationRequest,
    ResourceAllocationRequest,
    ResourceType,
    ResourceRequestAllocationStatus,
)
from eos.resource_allocation.exceptions import EosResourceRequestError
from eos.resource_allocation.resource_allocation_manager import ResourceAllocationManager
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.base_task import BaseTask
from eos.tasks.entities.task import TaskStatus
from eos.tasks.entities.task_execution_parameters import TaskExecutionParameters
from eos.tasks.exceptions import (
    EosTaskResourceAllocationError,
    EosTaskExecutionError,
    EosTaskValidationError,
    EosTaskExistsError, EosTaskCancellationError,
)
from eos.tasks.task_input_parameter_caster import TaskInputParameterCaster
from eos.tasks.task_manager import TaskManager
from eos.tasks.task_validator import TaskValidator


@dataclass
class TaskExecutionContext:
    experiment_id: str
    task_id: str
    task_ref: ObjectRef | None = None
    active_resource_request: ActiveResourceAllocationRequest = None


class TaskExecutor:
    def __init__(
        self,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        container_manager: ContainerManager,
        resource_allocation_manager: ResourceAllocationManager,
        configuration_manager: ConfigurationManager,
    ):
        self._task_manager = task_manager
        self._device_manager = device_manager
        self._container_manager = container_manager
        self._resource_allocation_manager = resource_allocation_manager
        self._configuration_manager = configuration_manager
        self._task_plugin_registry = configuration_manager.tasks
        self._task_validator = TaskValidator()
        self._task_input_parameter_caster = TaskInputParameterCaster()

        self._active_tasks: dict[tuple[str, str], TaskExecutionContext] = {}

        log.debug("Task executor initialized.")

    async def request_task_execution(
        self, task_parameters: TaskExecutionParameters, scheduled_task: ScheduledTask | None = None
    ) -> BaseTask.OutputType | None:
        """
        Request the execution of a task. Resources will first be requested to be allocated (if not pre-allocated)
        and then the task will be executed.

        :param task_parameters: Parameters for task execution
        :param scheduled_task: Scheduled task information, if applicable. This is populated by the EOS scheduler.
        :return: Output of the executed task

        :raises EosTaskExecutionError: If there's an error during task execution
        :raises EosTaskValidationError: If the task fails validation
        :raises EosTaskResourceAllocationError: If resource allocation fails
        """
        context = TaskExecutionContext(task_parameters.experiment_id, task_parameters.task_config.id)
        task_key = (context.experiment_id, context.task_id)
        self._active_tasks[task_key] = context

        try:
            containers = await self._prepare_containers(task_parameters)
            await self._initialize_task(task_parameters, containers)

            self._task_validator.validate(task_parameters.task_config)

            context.active_resource_request = (
                scheduled_task.allocated_resources
                if scheduled_task
                else await self._allocate_resources(task_parameters)
            )

            context.task_ref = await self._execute_task(task_parameters, containers)
            return await context.task_ref
        except EosTaskExistsError as e:
            raise EosTaskExecutionError(
                f"Error executing task '{context.task_id}' in experiment '{context.experiment_id}'"
            ) from e
        except EosTaskValidationError as e:
            await self._task_manager.fail_task(context.experiment_id, context.task_id)
            log.warning(f"EXP '{context.experiment_id}' - Failed task '{context.task_id}'.")
            raise EosTaskValidationError(
                f"Validation error for task '{context.task_id}' in experiment '{context.experiment_id}'"
            ) from e
        except EosTaskResourceAllocationError as e:
            await self._task_manager.fail_task(context.experiment_id, context.task_id)
            log.warning(f"EXP '{context.experiment_id}' - Failed task '{context.task_id}'.")
            raise EosTaskResourceAllocationError(
                f"Failed to allocate resources for task '{context.task_id}' in experiment '{context.experiment_id}'"
            ) from e
        except Exception as e:
            await self._task_manager.fail_task(context.experiment_id, context.task_id)
            log.warning(f"EXP '{context.experiment_id}' - Failed task '{context.task_id}'.")
            raise EosTaskExecutionError(
                f"Error executing task '{context.task_id}' in experiment '{context.experiment_id}'"
            ) from e
        finally:
            if context.active_resource_request and not scheduled_task:
                # We only release resources if they were allocated by the task executor and not the scheduler
                await self._release_resources(context.active_resource_request)

            if task_key in self._active_tasks:
                del self._active_tasks[task_key]

    async def request_task_cancellation(self, experiment_id: str, task_id: str) -> None:
        """
        Request the cancellation of a running task.

        :param experiment_id: ID of the experiment
        :param task_id: ID of the task to cancel
        """
        task_key = (experiment_id, task_id)
        context = self._active_tasks.get(task_key)
        if not context:
            raise EosTaskCancellationError(
                f"Cannot cancel task '{task_id}' in experiment '{experiment_id}' as it does not exist.")

        if context.task_ref:
            ray.cancel(context.task_ref, recursive=True)

        if context.active_resource_request:
            await self._resource_allocation_manager.abort_active_request(context.active_resource_request.id)
            await self._resource_allocation_manager.process_active_requests()

        await self._task_manager.cancel_task(experiment_id, task_id)
        del self._active_tasks[task_key]
        log.warning(f"EXP '{experiment_id}' - Cancelled task '{task_id}'.")

    async def _prepare_containers(self, execution_parameters: TaskExecutionParameters) -> dict[str, Container]:
        containers = execution_parameters.task_config.containers
        fetched_containers = await asyncio.gather(
            *[self._container_manager.get_container(container_id) for container_id in containers.values()]
        )

        return dict(zip(containers.keys(), fetched_containers, strict=True))

    async def _initialize_task(
        self, execution_parameters: TaskExecutionParameters, containers: dict[str, Container]
    ) -> None:
        experiment_id, task_id = execution_parameters.experiment_id, execution_parameters.task_config.id
        log.debug(f"Execution of task '{task_id}' for experiment '{experiment_id}' has been requested")

        task = await self._task_manager.get_task(experiment_id, task_id)
        if task and task.status == TaskStatus.RUNNING:
            log.warning(f"Found running task '{task_id}' for experiment '{experiment_id}'. Restarting it.")
            await self.request_task_cancellation(experiment_id, task_id)
            await self._task_manager.delete_task(experiment_id, task_id)

        await self._task_manager.create_task(
            experiment_id=experiment_id,
            task_id=task_id,
            task_type=execution_parameters.task_config.type,
            devices=execution_parameters.task_config.devices,
            parameters=execution_parameters.task_config.parameters,
            containers=containers,
        )

    async def _allocate_resources(
        self, execution_parameters: TaskExecutionParameters
    ) -> ActiveResourceAllocationRequest:
        resource_request = self._create_resource_request(execution_parameters)
        return await self._request_resources(resource_request, execution_parameters.resource_allocation_timeout)

    def _get_device_actor_references(self, task_parameters: TaskExecutionParameters) -> list[DeviceActorReference]:
        return [
            DeviceActorReference(
                id=device.id,
                lab_id=device.lab_id,
                type=self._configuration_manager.labs[device.lab_id].devices[device.id].type,
                actor_handle=self._device_manager.get_device_actor(device.lab_id, device.id),
            )
            for device in task_parameters.task_config.devices
        ]

    async def _execute_task(
        self,
        task_execution_parameters: TaskExecutionParameters,
        containers: dict[str, Container],
    ) -> ObjectRef:
        experiment_id, task_id = task_execution_parameters.experiment_id, task_execution_parameters.task_config.id
        device_actor_references = self._get_device_actor_references(task_execution_parameters)
        task_class_type = self._task_plugin_registry.get_task_class_type(task_execution_parameters.task_config.type)
        parameters = task_execution_parameters.task_config.parameters
        if not isinstance(parameters, dict):
            parameters = OmegaConf.to_object(parameters)

        parameters = self._task_input_parameter_caster.cast_input_parameters(
            task_id, task_execution_parameters.task_config.type, parameters
        )

        @ray.remote(num_cpus=0)
        def _ray_execute_task(
            _experiment_id: str,
            _task_id: str,
            _devices_actor_references: list[DeviceActorReference],
            _parameters: dict[str, Any],
            _containers: dict[str, Container],
        ) -> tuple:
            task = task_class_type(_experiment_id, _task_id)
            devices = DeviceActorWrapperRegistry(_devices_actor_references)
            return task.execute(devices, _parameters, _containers)

        await self._task_manager.start_task(experiment_id, task_id)
        log.info(f"EXP '{experiment_id}' - Started task '{task_id}'.")

        return _ray_execute_task.options(name=f"{experiment_id}.{task_id}").remote(
            experiment_id,
            task_id,
            device_actor_references,
            parameters,
            containers,
        )

    @staticmethod
    def _create_resource_request(
        task_parameters: TaskExecutionParameters,
    ) -> ResourceAllocationRequest:
        task_id, experiment_id = task_parameters.task_config.id, task_parameters.experiment_id
        resource_allocation_priority = task_parameters.resource_allocation_priority

        request = ResourceAllocationRequest(
            requester=task_id,
            experiment_id=experiment_id,
            reason=f"Resources required for task '{task_id}'",
            priority=resource_allocation_priority,
        )

        for device in task_parameters.task_config.devices:
            request.add_resource(device.id, device.lab_id, ResourceType.DEVICE)

        for container_id in task_parameters.task_config.containers.values():
            request.add_resource(container_id, "", ResourceType.CONTAINER)

        return request

    async def _request_resources(
        self, resource_request: ResourceAllocationRequest, timeout: int = 30
    ) -> ActiveResourceAllocationRequest:
        allocation_event = asyncio.Event()
        active_request = None

        def resource_request_callback(request: ActiveResourceAllocationRequest) -> None:
            nonlocal active_request
            active_request = request
            allocation_event.set()

        active_resource_request = await self._resource_allocation_manager.request_resources(
            resource_request, resource_request_callback
        )

        if active_resource_request.status == ResourceRequestAllocationStatus.ALLOCATED:
            return active_resource_request

        await self._resource_allocation_manager.process_active_requests()

        try:
            await asyncio.wait_for(allocation_event.wait(), timeout)
        except asyncio.TimeoutError as e:
            await self._resource_allocation_manager.abort_active_request(active_resource_request.id)
            raise EosTaskResourceAllocationError(
                f"Resource allocation timed out after {timeout} seconds for task '{resource_request.requester}'. "
                f"Aborting all resource allocations for this task."
            ) from e

        if not active_request:
            raise EosTaskResourceAllocationError(f"Error allocating resources for task '{resource_request.requester}'")

        return active_request

    async def _release_resources(self, active_request: ActiveResourceAllocationRequest) -> None:
        try:
            await self._resource_allocation_manager.release_resources(active_request)
            await self._resource_allocation_manager.process_active_requests()
        except EosResourceRequestError as e:
            raise EosTaskExecutionError(f"Error releasing task '{active_request.request.requester}' resources") from e
