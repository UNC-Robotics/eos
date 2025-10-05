import asyncio
from dataclasses import dataclass
from typing import Any

import ray
from ray import ObjectRef

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task import TaskConfig
from eos.devices.device_actor_utils import DeviceActorReference, create_device_actor_dict
from eos.devices.device_manager import DeviceManager
from eos.resources.entities.resource import Resource
from eos.resources.resource_manager import ResourceManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.allocation.entities.allocation_request import (
    ActiveAllocationRequest,
    AllocationRequest,
    AllocationType,
    AllocationRequestStatus,
)
from eos.allocation.exceptions import EosAllocationRequestError
from eos.allocation.allocation_manager import AllocationManager
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
from eos.utils.di.di_container import inject


@dataclass
class TaskExecutionContext:
    """Represents the execution context and state of a task."""

    experiment_name: str | None
    task_name: str

    task_definition: TaskDefinition

    scheduled_task: ScheduledTask | None = None

    task_ref: ObjectRef | None = None
    active_allocation_request: ActiveAllocationRequest | None = None

    initialized: bool = False
    execution_started: bool = False

    @property
    def task_key(self) -> tuple[str, str]:
        """Returns the unique identifier tuple for this task."""
        return self.experiment_name, self.task_name


class TaskExecutor:
    """Manages the execution lifecycle of tasks in the system."""

    @inject
    def __init__(
        self,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        resource_manager: ResourceManager,
        allocation_manager: AllocationManager,
        configuration_manager: ConfigurationManager,
        db_interface: AbstractSqlDbInterface,
    ):
        self._task_manager = task_manager
        self._device_manager = device_manager
        self._resource_manager = resource_manager
        self._allocation_manager = allocation_manager
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
            task_definition.experiment_name, task_definition.name, task_definition, scheduled_task=scheduled_task
        )

        async with self._lock:
            if context.task_key in self._pending_tasks:
                raise EosTaskExistsError(f"Task {context.task_key} is already pending execution")

            if scheduled_task:
                context.active_allocation_request = scheduled_task.allocations

            future = asyncio.Future()
            self._pending_tasks[context.task_key] = context
            self._task_futures[context.task_key] = future

        return await future

    async def cancel_task(self, experiment_name: str | None, task_name: str) -> None:
        """
        Request cancellation of a running task.

        :param experiment_name: Name of the experiment containing the task
        :param task_name: Name of the task to cancel
        """
        task_key = (experiment_name, task_name)
        context = self._pending_tasks.get(task_key)
        if not context:
            return

        if context.task_ref:
            ray.cancel(context.task_ref, force=True)

        async with self._db_interface.get_async_session() as db:
            if context.active_allocation_request and not context.scheduled_task:
                await self._allocation_manager.abort_request(db, context.active_allocation_request.id)
            await self._task_manager.cancel_task(db, context.experiment_name, context.task_name)

        if context.task_key in self._task_futures:
            self._task_futures[context.task_key].cancel()
            del self._task_futures[context.task_key]

        if context.task_key in self._pending_tasks:
            del self._pending_tasks[context.task_key]

        if experiment_name:
            log.warning(f"EXP '{experiment_name}' - Cancelled task '{task_name}'.")
        else:
            log.warning(f"Cancelled on-demand task '{task_name}'.")

    async def process_tasks(self) -> None:
        """Process all pending tasks through their execution lifecycle stages."""
        async with self._lock:
            async with self._db_interface.get_async_session() as db:
                await self._allocation_manager.process_requests(db)

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

        if await self._needs_allocations(context):
            await self._make_task_allocations(db, context)
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

            # Unpack task result - tasks should return (output_parameters, output_resources, output_files) or None
            if result is None:
                output_parameters, output_resources, output_files = {}, {}, {}
            else:
                output_parameters, output_resources, output_files = result

            for resource in output_resources.values():
                await self._resource_manager.update_resource(db, resource)

            for file_name, file_data in output_files.items():
                self._task_manager.add_task_output_file(
                    context.experiment_name, context.task_name, file_name, file_data
                )

            await self._task_manager.add_task_output(
                db,
                context.experiment_name,
                context.task_name,
                output_parameters,
                output_resources,
                list(output_files.keys()),
            )

            await self._task_manager.complete_task(db, context.experiment_name, context.task_name)

            if context.experiment_name:
                log.info(f"EXP '{context.experiment_name}' - Completed task '{context.task_name}'.")
            else:
                log.info(f"Completed on-demand task '{context.task_name}'.")

            self._task_futures[context.task_key].set_result((output_parameters, output_resources, output_files))

            await self._cleanup_task_allocations(context, db)
        except Exception:
            raise

    async def _initialize_task(self, db: AsyncDbSession, context: TaskExecutionContext) -> None:
        """Initialize task for execution."""
        task_config = context.task_definition.to_config()
        context.task_definition.input_resources = await self._prepare_resources(db, task_config)

        task_definition = context.task_definition
        experiment_name, task_name = task_definition.experiment_name, task_definition.name
        log.debug(f"Execution of task '{task_name}' for experiment '{experiment_name}' has been requested")

        task = await self._task_manager.get_task(db, experiment_name, task_name)
        if task and task.status == TaskStatus.RUNNING:
            log.warning(f"Found running task '{task_name}' for experiment '{experiment_name}'. Restarting it.")
            await self.cancel_task(experiment_name, task_name)
            await self._task_manager.delete_task(db, experiment_name, task_name)

        await self._task_manager.create_task(db, task_definition)
        await db.commit()
        self._task_validator.validate(task_config)

    async def _needs_allocations(self, context: TaskExecutionContext) -> bool:
        """Check if task needs allocations of devices or resources."""
        if not context.task_definition.devices and not context.task_definition.input_resources:
            return False

        return not context.active_allocation_request or (
            (
                context.active_allocation_request
                and context.active_allocation_request.status != AllocationRequestStatus.ALLOCATED
            )
            and not context.scheduled_task
        )

    async def _ready_for_execution(self, context: TaskExecutionContext) -> bool:
        """Check if task is ready for execution."""
        if not context.task_definition.devices and not context.task_definition.input_resources:
            return not context.execution_started

        return (
            context.active_allocation_request
            and context.active_allocation_request.status == AllocationRequestStatus.ALLOCATED
            and not context.execution_started
        )

    async def _make_task_allocations(self, db: AsyncDbSession, context: TaskExecutionContext) -> None:
        """Allocate devices and resources for task execution."""
        allocation_request = self._create_allocation_request(context.task_definition)
        context.active_allocation_request = await self._allocation_manager.request_allocations(
            db, allocation_request, lambda req: None
        )

    async def _handle_task_failure(self, db: AsyncDbSession, context: TaskExecutionContext, error: Exception) -> None:
        """Handle task execution failure."""
        self._task_futures[context.task_key].set_exception(error)
        await self._task_manager.fail_task(db, context.experiment_name, context.task_name)

        if context.experiment_name:
            log.warning(f"EXP '{context.experiment_name}' - Failed task '{context.task_name}'.")
        else:
            log.warning(f"Failed on-demand task '{context.task_name}'.")

        await self._cleanup_task_allocations(context, db)
        await db.commit()

        if context.experiment_name:
            raise EosTaskExecutionError(
                f"Error executing task '{context.task_name}' in experiment '{context.experiment_name}': {error}"
            ) from error

        raise EosTaskExecutionError(f"Error executing on-demand task '{context.task_name}': {error}")

    async def _cleanup_task_allocations(self, context: TaskExecutionContext, db: AsyncDbSession) -> None:
        """Clean up task allocations and state."""
        if context.active_allocation_request and not context.scheduled_task:
            try:
                await self._allocation_manager.release_allocations(db, context.active_allocation_request)
            except EosAllocationRequestError as e:
                raise EosTaskExecutionError(
                    f"Error releasing task's '{context.active_allocation_request.requester}' allocations"
                ) from e

        if context.task_key in self._task_futures:
            del self._task_futures[context.task_key]
        if context.task_key in self._pending_tasks:
            del self._pending_tasks[context.task_key]

    async def _prepare_resources(self, db: AsyncDbSession, task_config: TaskConfig) -> dict[str, Resource]:
        """Prepare resources for task execution."""
        resources = task_config.resources
        fetched_resources = await asyncio.gather(
            *[self._resource_manager.get_resource(db, resource_name) for resource_name in resources.values()]
        )
        return dict(zip(resources.keys(), fetched_resources, strict=True))

    def _get_device_actor_references(self, task_definition: TaskDefinition) -> dict[str, DeviceActorReference]:
        """Get device actor references for task execution.

        Returns a dict mapping device name (from task spec/config) to DeviceActorReference.
        """
        return {
            device_name: DeviceActorReference(
                name=device.name,
                lab_name=device.lab_name,
                type=self._configuration_manager.labs[device.lab_name].devices[device.name].type,
                actor_handle=self._device_manager.get_device_actor(device.lab_name, device.name),
                meta=self._configuration_manager.labs[device.lab_name].devices[device.name].meta,
            )
            for device_name, device in task_definition.devices.items()
        }

    async def _execute_task(self, db: AsyncDbSession, task_definition: TaskDefinition) -> ObjectRef:
        """Execute the task using Ray."""
        experiment_name, task_name = task_definition.experiment_name, task_definition.name
        device_actor_references = self._get_device_actor_references(task_definition)
        task_class_type = self._task_plugin_registry.get_plugin_class_type(task_definition.type)
        input_parameters = self._task_input_parameter_caster.cast_input_parameters(task_definition)

        @ray.remote(num_cpus=0)
        def _ray_execute_task(
            _experiment_name: str,
            _task_name: str,
            _devices_actor_references: dict[str, DeviceActorReference],
            _parameters: dict[str, Any],
            _resources: dict[str, Resource],
        ) -> tuple:
            task = task_class_type(_experiment_name, _task_name)
            devices = create_device_actor_dict(_devices_actor_references)
            return asyncio.run(task.execute(devices, _parameters, _resources))

        await self._task_manager.start_task(db, experiment_name, task_name)
        log_msg = (
            f"EXP '{experiment_name}' - Started task '{task_name}'."
            if task_definition.experiment_name
            else f"Started on-demand task '{task_name}'."
        )
        log.info(log_msg)

        return _ray_execute_task.options(name=f"{experiment_name}.{task_name}").remote(
            experiment_name,
            task_name,
            device_actor_references,
            input_parameters,
            task_definition.input_resources,
        )

    @staticmethod
    def _create_allocation_request(
        task_definition: TaskDefinition,
    ) -> AllocationRequest | None:
        """
        Create an exclusive allocation request for devices and resources for task execution.
        Returns None if no allocations are needed.
        """
        # Skip allocation if no devices or resources are needed
        if not task_definition.devices and not task_definition.input_resources:
            return None

        request = AllocationRequest(
            requester=task_definition.name,
            experiment_name=task_definition.experiment_name,
            priority=task_definition.priority,
            timeout=task_definition.allocation_timeout,
            reason=f"Resources required for task '{task_definition.name}'",
        )

        for device in task_definition.devices.values():
            request.add_allocation(device.name, device.lab_name, AllocationType.DEVICE)

        for resource in task_definition.input_resources.values():
            request.add_allocation(resource.name, "", AllocationType.RESOURCE)

        return request

    @property
    def has_work(self) -> bool:
        return bool(self._pending_tasks) or bool(self._task_futures)
