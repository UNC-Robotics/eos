import asyncio
from dataclasses import dataclass
from typing import Any

import ray
from ray import ObjectRef

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task import TaskConfig
from eos.containers.container_manager import ContainerManager
from eos.containers.entities.container import Container
from eos.devices.device_actor_wrapper_registry import DeviceActorReference, DeviceActorWrapperRegistry
from eos.devices.device_manager import DeviceManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
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
from eos.tasks.entities.task import TaskStatus, TaskDefinition
from eos.tasks.exceptions import (
    EosTaskExecutionError,
    EosTaskExistsError,
)
from eos.tasks.task_input_parameter_caster import TaskInputParameterCaster
from eos.tasks.task_manager import TaskManager
from eos.tasks.validation.task_validator import TaskValidator
from eos.utils.di.di_container import inject_all


@dataclass
class TaskExecutionContext:
    """Represents the execution context and state of a task."""

    experiment_id: str | None
    task_id: str

    task_definition: TaskDefinition

    scheduled_task: ScheduledTask | None = None

    task_ref: ObjectRef | None = None
    active_resource_request: ActiveResourceAllocationRequest | None = None

    initialized: bool = False
    execution_started: bool = False

    @property
    def task_key(self) -> tuple[str, str]:
        """Returns the unique identifier tuple for this task."""
        return self.experiment_id, self.task_id


class TaskExecutor:
    """Manages the execution lifecycle of tasks in the system."""

    @inject_all
    def __init__(
        self,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        container_manager: ContainerManager,
        resource_allocation_manager: ResourceAllocationManager,
        configuration_manager: ConfigurationManager,
        db_interface: AbstractSqlDbInterface,
    ):
        self._task_manager = task_manager
        self._device_manager = device_manager
        self._container_manager = container_manager
        self._resource_allocation_manager = resource_allocation_manager
        self._configuration_manager = configuration_manager
        self._db_interface = db_interface

        self._task_plugin_registry = configuration_manager.tasks
        self._task_validator = TaskValidator(configuration_manager)
        self._task_input_parameter_caster = TaskInputParameterCaster()

        self._pending_tasks: dict[tuple[str, str], TaskExecutionContext] = {}
        self._task_futures: dict[tuple[str, str], asyncio.Future] = {}
        self._lock = asyncio.Lock()

        log.debug("Task executor initialized.")

    async def request_task_execution(
        self,
        task_definition: TaskDefinition,
        scheduled_task: ScheduledTask | None = None,
    ) -> BaseTask.OutputType | None:
        """Request the execution of a new task."""
        context = TaskExecutionContext(
            task_definition.experiment_id, task_definition.id, task_definition, scheduled_task=scheduled_task
        )

        async with self._lock:
            if context.task_key in self._pending_tasks:
                raise EosTaskExistsError(f"Task {context.task_key} is already pending execution")

            if scheduled_task:
                context.active_resource_request = scheduled_task.allocated_resources

            future = asyncio.Future()
            self._pending_tasks[context.task_key] = context
            self._task_futures[context.task_key] = future

        return await future

    async def cancel_task(self, experiment_id: str | None, task_id: str) -> None:
        """
        Request cancellation of a running task.

        :param experiment_id: ID of the experiment containing the task
        :param task_id: ID of the task to cancel
        """
        task_key = (experiment_id, task_id)
        context = self._pending_tasks.get(task_key)
        if not context:
            return

        if context.task_ref:
            ray.cancel(context.task_ref, force=True)

        async with self._db_interface.get_async_session() as db:
            if context.active_resource_request and not context.scheduled_task:
                await self._resource_allocation_manager.abort_request(db, context.active_resource_request.id)
            await self._task_manager.cancel_task(db, context.experiment_id, context.task_id)

        if context.task_key in self._task_futures:
            self._task_futures[context.task_key].cancel()
            del self._task_futures[context.task_key]

        if context.task_key in self._pending_tasks:
            del self._pending_tasks[context.task_key]

        if experiment_id:
            log.warning(f"EXP '{experiment_id}' - Cancelled task '{task_id}'.")
        else:
            log.warning(f"Cancelled on-demand task '{task_id}'.")

    async def process_tasks(self) -> None:
        """Process all pending tasks through their execution lifecycle stages."""
        async with self._lock:
            async with self._db_interface.get_async_session() as db:
                await self._resource_allocation_manager.process_requests(db)

            tasks_to_process = list(self._pending_tasks.values())
            if not tasks_to_process:
                return

            await asyncio.gather(
                *(self._process_single_task(context) for context in tasks_to_process), return_exceptions=True
            )

    async def _process_single_task(self, context: TaskExecutionContext) -> None:
        """
        Process a single task through its lifecycle stages.

        :param context: The execution context for the task
        """
        async with self._db_interface.get_async_session() as db:
            try:
                await self._execute_task_lifecycle(db, context)
            except Exception as e:
                await self._handle_task_failure(db, context, e)

    async def _execute_task_lifecycle(self, db: AsyncDbSession, context: TaskExecutionContext) -> None:
        """Execute the main lifecycle stages of a task."""
        if not context.initialized:
            await self._initialize_task(db, context)
            context.initialized = True

        if await self._needs_resource_allocation(context):
            await self._allocate_task_resources(db, context)
            return

        if await self._ready_for_execution(context):
            context.task_ref = await self._execute_task(db, context.task_definition)
            context.execution_started = True
            return

        if context.execution_started and context.task_ref:
            await self._check_task_completion(db, context)

    async def _check_task_completion(self, db: AsyncDbSession, context: TaskExecutionContext) -> None:
        """Check if task has completed and process its output if done."""
        if not ray.wait([context.task_ref], timeout=0)[0]:
            return

        try:
            result = await context.task_ref
            if not result:
                return

            output_parameters, output_containers, output_files = result

            for container in output_containers.values():
                await self._container_manager.update_container(db, container)

            for file_name, file_data in output_files.items():
                self._task_manager.add_task_output_file(context.experiment_id, context.task_id, file_name, file_data)

            await self._task_manager.add_task_output(
                db,
                context.experiment_id,
                context.task_id,
                output_parameters,
                output_containers,
                list(output_files.keys()),
            )

            await self._task_manager.complete_task(db, context.experiment_id, context.task_id)

            if context.experiment_id:
                log.info(f"EXP '{context.experiment_id}' - Completed task '{context.task_id}'.")
            else:
                log.info(f"Completed on-demand task '{context.task_id}'.")

            self._task_futures[context.task_key].set_result(result)
        finally:
            await self._cleanup_task_resources(context, db)

    async def _initialize_task(self, db: AsyncDbSession, context: TaskExecutionContext) -> None:
        """Initialize task for execution."""
        task_config = context.task_definition.to_config()
        context.task_definition.input_containers = await self._prepare_containers(db, task_config)

        task_definition = context.task_definition
        experiment_id, task_id = task_definition.experiment_id, task_definition.id
        log.debug(f"Execution of task '{task_id}' for experiment '{experiment_id}' has been requested")

        task = await self._task_manager.get_task(db, experiment_id, task_id)
        if task and task.status == TaskStatus.RUNNING:
            log.warning(f"Found running task '{task_id}' for experiment '{experiment_id}'. Restarting it.")
            await self.cancel_task(experiment_id, task_id)
            await self._task_manager.delete_task(db, experiment_id, task_id)

        await self._task_manager.create_task(db, task_definition)
        await db.commit()
        self._task_validator.validate(task_config)

    @staticmethod
    async def _needs_resource_allocation(context: TaskExecutionContext) -> bool:
        """Check if task needs resource allocation."""
        if not context.task_definition.devices and not context.task_definition.input_containers:
            return False

        return (
            not context.active_resource_request
            or (
                context.active_resource_request
                and context.active_resource_request.status != ResourceRequestAllocationStatus.ALLOCATED
            )
            and not context.scheduled_task
        )

    @staticmethod
    async def _ready_for_execution(context: TaskExecutionContext) -> bool:
        """Check if task is ready for execution."""
        if not context.task_definition.devices and not context.task_definition.input_containers:
            return not context.execution_started

        return (
            context.active_resource_request
            and context.active_resource_request.status == ResourceRequestAllocationStatus.ALLOCATED
            and not context.execution_started
        )

    async def _allocate_task_resources(self, db: AsyncDbSession, context: TaskExecutionContext) -> None:
        """Allocate resources for task execution."""
        resource_request = self._create_resource_request(context.task_definition)
        context.active_resource_request = await self._resource_allocation_manager.request_resources(
            db, resource_request, lambda req: None
        )

    async def _handle_task_failure(self, db: AsyncDbSession, context: TaskExecutionContext, error: Exception) -> None:
        """Handle task execution failure."""
        self._task_futures[context.task_key].set_exception(error)
        await self._task_manager.fail_task(db, context.experiment_id, context.task_id)

        if context.experiment_id:
            log.warning(f"EXP '{context.experiment_id}' - Failed task '{context.task_id}'.")
        else:
            log.warning(f"Failed on-demand task '{context.task_id}'.")

        await self._cleanup_task_resources(context, db)
        await db.commit()

        if context.experiment_id:
            raise EosTaskExecutionError(
                f"Error executing task '{context.task_id}' in experiment '{context.experiment_id}': {error}"
            ) from error

        raise EosTaskExecutionError(f"Error executing on-demand task '{context.task_id}': {error}")

    async def _cleanup_task_resources(self, context: TaskExecutionContext, db: AsyncDbSession) -> None:
        """Clean up task resources and state."""
        if context.active_resource_request and not context.scheduled_task:
            try:
                await self._resource_allocation_manager.release_resources(db, context.active_resource_request)
            except EosResourceRequestError as e:
                raise EosTaskExecutionError(
                    f"Error releasing task's '{context.active_resource_request.requester}' resources"
                ) from e

        if context.task_key in self._task_futures:
            del self._task_futures[context.task_key]
        if context.task_key in self._pending_tasks:
            del self._pending_tasks[context.task_key]

    async def _prepare_containers(self, db: AsyncDbSession, task_config: TaskConfig) -> dict[str, Container]:
        """Prepare containers for task execution."""
        containers = task_config.containers
        fetched_containers = await asyncio.gather(
            *[self._container_manager.get_container(db, container_id) for container_id in containers.values()]
        )
        return dict(zip(containers.keys(), fetched_containers, strict=True))

    def _get_device_actor_references(self, task_definition: TaskDefinition) -> list[DeviceActorReference]:
        """Get device actor references for task execution."""
        return [
            DeviceActorReference(
                id=device.id,
                lab_id=device.lab_id,
                type=self._configuration_manager.labs[device.lab_id].devices[device.id].type,
                actor_handle=self._device_manager.get_device_actor(device.lab_id, device.id),
            )
            for device in task_definition.devices
        ]

    async def _execute_task(self, db: AsyncDbSession, task_definition: TaskDefinition) -> ObjectRef:
        """Execute the task using Ray."""
        experiment_id, task_id = task_definition.experiment_id, task_definition.id
        device_actor_references = self._get_device_actor_references(task_definition)
        task_class_type = self._task_plugin_registry.get_plugin_class_type(task_definition.type)
        input_parameters = self._task_input_parameter_caster.cast_input_parameters(task_definition)

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
            return asyncio.run(task.execute(devices, _parameters, _containers))

        await self._task_manager.start_task(db, experiment_id, task_id)
        log_msg = (
            f"EXP '{experiment_id}' - Started task '{task_id}'."
            if task_definition.experiment_id
            else f"Started on-demand task '{task_id}'."
        )
        log.info(log_msg)

        return _ray_execute_task.options(name=f"{experiment_id}.{task_id}").remote(
            experiment_id,
            task_id,
            device_actor_references,
            input_parameters,
            task_definition.input_containers,
        )

    @staticmethod
    def _create_resource_request(
        task_definition: TaskDefinition,
    ) -> ResourceAllocationRequest | None:
        """
        Create a resource allocation request for task execution.
        Returns None if no resources are needed.
        """
        # Skip resource allocation if no resources are needed
        if not task_definition.devices and not task_definition.input_containers:
            return None

        request = ResourceAllocationRequest(
            requester=task_definition.id,
            experiment_id=task_definition.experiment_id,
            priority=task_definition.priority,
            timeout=task_definition.resource_allocation_timeout,
            reason=f"Resources required for task '{task_definition.id}'",
        )

        for device in task_definition.devices:
            request.add_resource(device.id, device.lab_id, ResourceType.DEVICE)

        for container in task_definition.input_containers.values():
            request.add_resource(container.id, "", ResourceType.CONTAINER)

        return request

    @property
    def has_work(self) -> bool:
        return bool(self._pending_tasks) or bool(self._task_futures)
