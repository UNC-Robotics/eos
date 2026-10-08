import asyncio
import traceback

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.tasks.entities.task import Task, TaskStatus, TaskSubmission
from eos.tasks.exceptions import EosTaskCancellationError, EosTaskExecutionError
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.tasks.validation.task_validator import TaskValidator
from eos.utils.di.di_container import inject


class TaskService:
    """
    Top-level task functionality integration.
    Exposes an interface for submission, monitoring, and cancellation of tasks.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        task_manager: TaskManager,
        task_executor: TaskExecutor,
        scheduler: AbstractScheduler,
        db_interface: AbstractSqlDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._task_manager = task_manager
        self._task_executor = task_executor
        self._scheduler = scheduler
        self._db_interface = db_interface

        self._on_demand_futures: dict[str, asyncio.Task] = {}
        self._queued_on_demand: set[str] = set()

    async def get_task(self, db: AsyncDbSession, protocol_run_name: str, task_name: str) -> Task:
        return await self._task_manager.get_task(db, protocol_run_name, task_name)

    async def submit_task(self, db: AsyncDbSession, task_submission: TaskSubmission) -> None:
        """Submit an on-demand task. Routes through the scheduler for unified scheduling."""
        task_spec = self._configuration_manager.task_specs.get_spec_by_type(task_submission.type)
        if not task_spec:
            raise EosTaskExecutionError(f"Unknown task type '{task_submission.type}'.")

        TaskValidator(self._configuration_manager).validate(task_submission.to_def())

        name = task_submission.name
        if (
            name in self._on_demand_futures
            or name in self._queued_on_demand
            or await self._task_manager.get_task(db, None, name)
        ):
            raise EosTaskExecutionError(f"Cannot submit duplicate on-demand task '{name}'.")

        try:
            scheduled_task = await self._scheduler.submit_on_demand_task(db, task_submission)
            if scheduled_task:
                self._on_demand_futures[name] = asyncio.create_task(
                    self._task_executor.request_task_execution(task_submission, scheduled_task)
                )
            else:
                # Queued in the scheduler and retried by process_pending_on_demand()
                self._queued_on_demand.add(name)
            log.info(f"Submitted on-demand task '{task_submission.name}'.")
        except EosTaskExecutionError:
            log.error(f"Failed to submit task '{task_submission.name}': {traceback.format_exc()}")
            raise

    async def cancel_task(self, task_name: str, protocol_run_name: str | None = None) -> None:
        if protocol_run_name is None and await self._scheduler.cancel_on_demand_task(task_name):
            self._queued_on_demand.discard(task_name)
            log.warning(f"Cancelled queued on-demand task '{task_name}'.")
            return
        try:
            await self._task_executor.cancel_task(protocol_run_name, task_name)
        except EosTaskCancellationError:
            log.error(f"Failed to cancel task '{task_name}'.")
            raise

    async def fail_running_tasks(self, db: AsyncDbSession) -> None:
        running_tasks = await self._task_manager.get_tasks(db, status=TaskStatus.RUNNING.value)
        if not running_tasks:
            return

        task_keys = [(t.protocol_run_name, t.name) for t in running_tasks]
        await self._task_manager.fail_tasks_batch(
            db, task_keys, error_message="Task was running when the orchestrator restarted"
        )
        for task in running_tasks:
            log.warning(f"RUN '{task.protocol_run_name}' - Failed task '{task.name}'.")
        log.warning("All running tasks have been marked as failed. Please review the state of the system.")

    async def get_task_types(self) -> list[str]:
        return [task.type for task in self._configuration_manager.task_specs.get_all_specs().values()]

    async def process_pending_on_demand(self) -> None:
        """Retry queued on-demand tasks and dispatch any that become schedulable."""
        # Clean up completed futures
        completed = [name for name, future in self._on_demand_futures.items() if future.done()]
        for name in completed:
            future = self._on_demand_futures.pop(name)
            try:
                await future
            except (EosTaskCancellationError, asyncio.CancelledError):
                log.info(f"On-demand task '{name}' was cancelled.")
            except Exception:
                log.error(f"Failed on-demand task '{name}': {traceback.format_exc()}")

        # Retry queued tasks, committing their allocations before anything else can roll them back
        async with self._db_interface.get_async_session() as db:
            progress = await self._scheduler.process_pending_on_demand(db)

        for submission, scheduled_task in progress.scheduled:
            self._queued_on_demand.discard(submission.name)
            self._on_demand_futures[submission.name] = asyncio.create_task(
                self._task_executor.request_task_execution(submission, scheduled_task)
            )

        for submission in progress.timed_out:
            self._queued_on_demand.discard(submission.name)
            try:
                async with self._db_interface.get_async_session() as db:
                    await self._task_manager.create_task(db, submission)
                    await self._task_manager.fail_task(
                        db,
                        None,
                        submission.name,
                        error_message=(
                            f"Timed out after {submission.allocation_timeout}s waiting for devices or resources"
                        ),
                    )
            except Exception:
                log.error(
                    f"Failed to record the timeout of on-demand task '{submission.name}': {traceback.format_exc()}"
                )
