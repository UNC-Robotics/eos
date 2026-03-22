import asyncio
from dataclasses import dataclass
from typing import Any

import ray
from ray import ObjectRef

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import TaskDef
from eos.devices.device_actor_utils import DeviceActorReference, create_device_actor_dict
from eos.devices.device_manager import DeviceManager
from eos.resources.entities.resource import Resource
from eos.resources.resource_manager import ResourceManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.orchestration.work_signal import WorkSignal
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.base_task import BaseTask
from eos.tasks.entities.task import TaskStatus, TaskSubmission
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
    task_submission: TaskSubmission
    scheduled_task: ScheduledTask

    task_ref: ObjectRef | None = None
    initialized: bool = False
    execution_started: bool = False

    @property
    def task_key(self) -> tuple[str | None, str]:
        return self.experiment_name, self.task_name


class TaskExecutor:
    """Manages task execution lifecycle."""

    @inject
    def __init__(
        self,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        resource_manager: ResourceManager,
        configuration_manager: ConfigurationManager,
        scheduler: AbstractScheduler,
        db_interface: AbstractSqlDbInterface,
        work_signal: WorkSignal,
    ):
        self._task_manager = task_manager
        self._device_manager = device_manager
        self._resource_manager = resource_manager
        self._configuration_manager = configuration_manager
        self._scheduler = scheduler
        self._db_interface = db_interface
        self._work_signal = work_signal

        self._task_plugin_registry = configuration_manager.tasks
        self._task_validator = TaskValidator(configuration_manager)
        self._task_input_parameter_caster = TaskInputParameterCaster()

        self._pending_tasks: dict[tuple[str | None, str], TaskExecutionContext] = {}
        self._task_futures: dict[tuple[str | None, str], asyncio.Future] = {}
        self._lock = asyncio.Lock()

        log.debug("Task executor initialized.")

    async def request_task_execution(
        self,
        task_submission: TaskSubmission,
        scheduled_task: ScheduledTask,
    ) -> BaseTask.OutputType | None:
        context = TaskExecutionContext(
            task_submission.experiment_name, task_submission.name, task_submission, scheduled_task
        )

        async with self._lock:
            if context.task_key in self._pending_tasks:
                raise EosTaskExistsError(f"Task {context.task_key} is already pending execution")

            future = asyncio.Future()
            self._pending_tasks[context.task_key] = context
            self._task_futures[context.task_key] = future

        self._work_signal.signal()
        return await future

    async def cancel_task(self, experiment_name: str | None, task_name: str) -> None:
        task_key = (experiment_name, task_name)
        context = self._pending_tasks.get(task_key)
        if not context:
            return

        if context.task_ref:
            ray.cancel(context.task_ref, force=True)

        async with self._db_interface.get_async_session() as db:
            await self._task_manager.cancel_task(db, context.experiment_name, context.task_name)
            await self._scheduler.release_task(db, task_name, experiment_name)

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
        async with self._lock:
            tasks_to_process = list(self._pending_tasks.values())
            if not tasks_to_process:
                return

            results = await asyncio.gather(
                *(self._process_single_task(context) for context in tasks_to_process), return_exceptions=True
            )

            for context, result in zip(tasks_to_process, results, strict=True):
                if isinstance(result, Exception):
                    log.error(
                        f"Error processing task '{context.task_name}' for experiment "
                        f"'{context.experiment_name}': {result}"
                    )

    async def _process_single_task(self, context: TaskExecutionContext) -> None:
        async with self._db_interface.get_async_session() as db:
            try:
                await self._execute_task_lifecycle(db, context)
            except Exception as e:
                await self._handle_task_failure(db, context, e)

    async def _execute_task_lifecycle(self, db: AsyncDbSession, context: TaskExecutionContext) -> None:
        if not context.initialized:
            await self._initialize_task(db, context)
            context.initialized = True

        if not context.execution_started:
            context.task_ref = await self._execute_task(db, context.task_submission)
            context.execution_started = True
            return

        if context.execution_started and context.task_ref:
            await self._check_task_completion(db, context)

    async def _check_task_completion(self, db: AsyncDbSession, context: TaskExecutionContext) -> None:
        if not ray.wait([context.task_ref], timeout=0)[0]:
            return

        result = await context.task_ref

        if result is None:
            output_parameters, output_resources, output_files = {}, {}, {}
        else:
            output_parameters, output_resources, output_files = result

        for resource in output_resources.values():
            await self._resource_manager.update_resource(db, resource)

        for file_name, file_data in output_files.items():
            await self._task_manager.add_task_output_file(
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

        await self._scheduler.release_task(db, context.task_name, context.experiment_name)

        self._cleanup_task(context)

    async def _initialize_task(self, db: AsyncDbSession, context: TaskExecutionContext) -> None:
        task = context.task_submission.to_def()
        context.task_submission.input_resources = await self._prepare_resources(db, task)

        task_submission = context.task_submission
        experiment_name, task_name = task_submission.experiment_name, task_submission.name
        log.debug(f"Execution of task '{task_name}' for experiment '{experiment_name}' has been requested")

        existing_task = await self._task_manager.get_task(db, experiment_name, task_name)
        if existing_task and existing_task.status == TaskStatus.RUNNING:
            log.warning(f"Found running task '{task_name}' for experiment '{experiment_name}'. Restarting it.")
            await self.cancel_task(experiment_name, task_name)
            await self._task_manager.delete_task(db, experiment_name, task_name)

        await self._task_manager.create_task(db, task_submission)
        self._task_validator.validate(task)

    async def _handle_task_failure(self, db: AsyncDbSession, context: TaskExecutionContext, error: Exception) -> None:
        error_msg = f"{type(error).__name__}: {error}"
        try:
            self._task_futures[context.task_key].set_exception(error)
            await self._task_manager.fail_task(db, context.experiment_name, context.task_name, error_message=error_msg)

            if context.experiment_name:
                log.warning(f"EXP '{context.experiment_name}' - Failed task '{context.task_name}'.")
            else:
                log.warning(f"Failed on-demand task '{context.task_name}'.")

            await self._scheduler.release_task(db, context.task_name, context.experiment_name)
        finally:
            self._cleanup_task(context)

        if context.experiment_name:
            raise EosTaskExecutionError(
                f"Error executing task '{context.task_name}' in experiment '{context.experiment_name}': {error}"
            ) from error
        raise EosTaskExecutionError(f"Error executing on-demand task '{context.task_name}': {error}")

    def _cleanup_task(self, context: TaskExecutionContext) -> None:
        self._task_futures.pop(context.task_key, None)
        self._pending_tasks.pop(context.task_key, None)

    async def _prepare_resources(self, db: AsyncDbSession, task: TaskDef) -> dict[str, Resource]:
        resource_by_name = await self._resource_manager.get_resources_by_names(db, list(task.resources.values()))
        return {slot: resource_by_name[name] for slot, name in task.resources.items()}

    def _get_device_actor_references(self, task_submission: TaskSubmission) -> dict[str, DeviceActorReference]:
        return {
            device_name: DeviceActorReference(
                name=device.name,
                lab_name=device.lab_name,
                type=self._configuration_manager.labs[device.lab_name].devices[device.name].type,
                actor_handle=self._device_manager.get_device_actor(device.lab_name, device.name),
                meta=self._configuration_manager.labs[device.lab_name].devices[device.name].meta,
            )
            for device_name, device in task_submission.devices.items()
        }

    async def _execute_task(self, db: AsyncDbSession, task_submission: TaskSubmission) -> ObjectRef:
        experiment_name, task_name = task_submission.experiment_name, task_submission.name
        device_actor_references = self._get_device_actor_references(task_submission)
        task_class_type = self._task_plugin_registry.get_plugin_class_type(task_submission.type)
        input_parameters = self._task_input_parameter_caster.cast_input_parameters(task_submission)

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
            if task_submission.experiment_name
            else f"Started on-demand task '{task_name}'."
        )
        log.info(log_msg)

        return _ray_execute_task.options(name=f"{experiment_name}.{task_name}").remote(
            experiment_name,
            task_name,
            device_actor_references,
            input_parameters,
            task_submission.input_resources,
        )

    async def process_new_tasks(self) -> None:
        """Process only tasks that haven't started execution yet."""
        async with self._lock:
            new_tasks = [ctx for ctx in self._pending_tasks.values() if not ctx.execution_started]
            if not new_tasks:
                return

            results = await asyncio.gather(
                *(self._process_single_task(context) for context in new_tasks), return_exceptions=True
            )

            for context, result in zip(new_tasks, results, strict=True):
                if isinstance(result, Exception):
                    log.error(
                        f"Error processing new task '{context.task_name}' for experiment "
                        f"'{context.experiment_name}': {result}"
                    )

    @property
    def has_work(self) -> bool:
        return bool(self._pending_tasks) or bool(self._task_futures)
