import asyncio
from typing import Any

from eos.configuration.protocol_graph import ProtocolGraph
from eos.configuration import validation as validation_utils
from eos.protocols.entities.protocol_run import ProtocolRunStatus, ProtocolRun, ProtocolRunSubmission
from eos.protocols.exceptions import (
    EosProtocolRunExecutionError,
    EosProtocolRunTaskExecutionError,
    EosProtocolRunCancellationError,
)
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.entities.task import TaskSubmission
from eos.tasks.exceptions import EosTaskExecutionError, EosTaskCancellationError
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_input_resolver import TaskInputResolver
from eos.tasks.task_manager import TaskManager


class ProtocolExecutor:
    """Responsible for executing all the tasks of a single protocol run."""

    def __init__(
        self,
        protocol_run_submission: ProtocolRunSubmission,
        protocol_graph: ProtocolGraph,
        protocol_run_manager: ProtocolRunManager,
        task_manager: TaskManager,
        task_executor: TaskExecutor,
        scheduler: AbstractScheduler,
        db_interface: AbstractSqlDbInterface,
        campaign: str | None = None,
    ):
        self._protocol_run_submission = protocol_run_submission
        self._protocol_run_name = protocol_run_submission.name
        self._protocol = protocol_run_submission.type
        self._protocol_graph = protocol_graph
        self._campaign = campaign

        self._protocol_run_manager = protocol_run_manager
        self._task_manager = task_manager
        self._task_executor = task_executor
        self._scheduler = scheduler
        self._db_interface = db_interface
        self._task_input_resolver = TaskInputResolver(task_manager, protocol_run_manager)

        self._current_task_submissions: dict[str, TaskSubmission] = {}
        self._task_output_futures: dict[str, asyncio.Task] = {}
        self._protocol_run_status = None

    async def start_protocol_run(self, db: AsyncDbSession) -> None:
        """Start the protocol run and register the executor with the scheduler."""
        protocol_run_created = False
        try:
            protocol_run = await self._protocol_run_manager.get_protocol_run(db, self._protocol_run_name)
            if protocol_run:
                protocol_run_created = True  # Already exists
                await self._handle_existing_protocol_run(db, protocol_run)
            else:
                await self._create_new_protocol_run(db)
                protocol_run_created = True

            await self._scheduler.register_protocol_run(
                protocol_run_name=self._protocol_run_name,
                protocol=self._protocol,
                protocol_graph=self._protocol_graph,
            )

            await self._protocol_run_manager.start_protocol_run(db, self._protocol_run_name)
            self._protocol_run_status = ProtocolRunStatus.RUNNING

            action = "Resumed" if self._protocol_run_submission.resume else "Started"
            log.info(f"{action} protocol run '{self._protocol_run_name}'.")
        except EosProtocolRunExecutionError as e:
            if protocol_run_created:
                try:
                    await self._protocol_run_manager.fail_protocol_run(
                        db, self._protocol_run_name, error_message=str(e)
                    )
                    self._protocol_run_status = ProtocolRunStatus.FAILED
                except Exception as fail_err:
                    log.error(f"Failed to mark protocol run '{self._protocol_run_name}' as failed: {fail_err}")
            raise
        except Exception as e:
            if protocol_run_created:
                try:
                    await self._protocol_run_manager.fail_protocol_run(
                        db, self._protocol_run_name, error_message=str(e)
                    )
                    self._protocol_run_status = ProtocolRunStatus.FAILED
                except Exception as fail_err:
                    log.error(f"Failed to mark protocol run '{self._protocol_run_name}' as failed: {fail_err}")
            raise EosProtocolRunExecutionError(f"Failed to start protocol run '{self._protocol_run_name}'") from e

    async def _handle_existing_protocol_run(self, db: AsyncDbSession, protocol_run: ProtocolRun) -> None:
        """Handle cases when the protocol run already exists."""
        self._protocol_run_status = protocol_run.status

        if not self._protocol_run_submission.resume:
            if self._protocol_run_status in (
                ProtocolRunStatus.COMPLETED,
                ProtocolRunStatus.SUSPENDED,
                ProtocolRunStatus.CANCELLED,
                ProtocolRunStatus.FAILED,
            ):
                raise EosProtocolRunExecutionError(
                    f"Cannot start protocol run '{self._protocol_run_name}' as it already exists and is "
                    f"'{self._protocol_run_status.value}'. Please create a new protocol run or re-submit with "
                    f"'resume=True'."
                )
        else:
            await self._resume_protocol_run(db)

    async def cancel_protocol_run(self) -> None:
        """Cancel the protocol run."""
        async with self._db_interface.get_async_session() as db:
            protocol_run = await self._protocol_run_manager.get_protocol_run(db, self._protocol_run_name)
            if not protocol_run or protocol_run.status != ProtocolRunStatus.RUNNING:
                raise EosProtocolRunCancellationError(
                    f"Cannot cancel protocol run '{self._protocol_run_name}' with status '{protocol_run.status}'. "
                    f"It must be running."
                )

            log.warning(f"Cancelling protocol run '{self._protocol_run_name}'...")
            self._protocol_run_status = ProtocolRunStatus.CANCELLED

            await self._protocol_run_manager.cancel_protocol_run(db, self._protocol_run_name)
            await self._scheduler.unregister_protocol_run(db, self._protocol_run_name)

        await self._cancel_running_tasks()

        log.warning(f"Cancelled protocol run '{self._protocol_run_name}'.")

    async def progress_protocol_run(self, db: AsyncDbSession) -> bool:
        """
        Try to progress the protocol run by executing tasks.

        :return: True if the protocol run has been completed, False otherwise.
        """
        try:
            if self._protocol_run_status != ProtocolRunStatus.RUNNING:
                return self._protocol_run_status == ProtocolRunStatus.CANCELLED

            if await self._scheduler.is_protocol_run_completed(db, self._protocol_run_name):
                await self._complete_protocol_run(db)
                return True

            await self._process_completed_tasks(db)
            await self._execute_tasks(db)

            return False
        except Exception as e:
            await self._fail_protocol_run(db, error_message=str(e))
            raise EosProtocolRunExecutionError(f"Error executing protocol run '{self._protocol_run_name}'") from e

    async def _resume_protocol_run(self, db: AsyncDbSession) -> None:
        """Resume an existing protocol run."""
        await self._protocol_run_manager.delete_non_completed_tasks(db, self._protocol_run_name)
        log.info(f"Protocol run '{self._protocol_run_name}' resumed.")

    async def _create_new_protocol_run(self, db: AsyncDbSession) -> None:
        """
        Create a new protocol run.
        """
        parameters = self._protocol_run_submission.parameters or {}
        self._validate_parameters(parameters)
        await self._protocol_run_manager.create_protocol_run(db, self._protocol_run_submission, campaign=self._campaign)

    async def _cancel_running_tasks(self) -> None:
        """Cancel all running tasks in the protocol run."""
        cancellation_tasks = [
            self._task_executor.cancel_task(task_submission.protocol_run_name, task_submission.name)
            for task_submission in self._current_task_submissions.values()
        ]
        try:
            await asyncio.gather(*cancellation_tasks, return_exceptions=True)

        except EosTaskCancellationError as e:
            raise EosProtocolRunExecutionError(
                f"Error cancelling tasks of protocol run {self._protocol_run_name}. "
                f"Some tasks may not have been cancelled."
            ) from e
        except TimeoutError as e:
            raise EosProtocolRunExecutionError(
                f"Timeout while cancelling protocol run {self._protocol_run_name}. "
                f"Some tasks may not have been cancelled."
            ) from e

    async def _complete_protocol_run(self, db: AsyncDbSession) -> None:
        """Complete the protocol run and clean up."""
        await self._scheduler.unregister_protocol_run(db, self._protocol_run_name)
        await self._protocol_run_manager.complete_protocol_run(db, self._protocol_run_name)
        self._protocol_run_status = ProtocolRunStatus.COMPLETED
        log.info(f"Completed protocol run '{self._protocol_run_name}'.")

    async def _fail_protocol_run(self, db: AsyncDbSession, error_message: str | None = None) -> None:
        """Fail the protocol run and cancel any running tasks."""
        await self._scheduler.unregister_protocol_run(db, self._protocol_run_name)
        await self._protocol_run_manager.fail_protocol_run(db, self._protocol_run_name, error_message=error_message)
        self._protocol_run_status = ProtocolRunStatus.FAILED
        await db.commit()

        # Ensure any running tasks are cancelled to avoid orphan work
        try:
            await self._cancel_running_tasks()
        finally:
            log.warning(f"Failed protocol run '{self._protocol_run_name}'. All running tasks cancelled.")

    async def _process_completed_tasks(self, db: AsyncDbSession) -> None:
        """Process the output of completed tasks."""
        completed_tasks = [task_name for task_name, future in self._task_output_futures.items() if future.done()]
        for task_name in completed_tasks:
            try:
                self._task_output_futures[task_name].result()  # Just check for exceptions
            except EosTaskExecutionError as e:
                raise EosProtocolRunTaskExecutionError(
                    f"Error executing task '{task_name}' of protocol run '{self._protocol_run_name}'"
                ) from e
            finally:
                del self._task_output_futures[task_name]
                del self._current_task_submissions[task_name]

    async def _execute_tasks(self, db: AsyncDbSession) -> None:
        """Request and execute new tasks from the scheduler."""
        new_scheduled_tasks = await self._scheduler.request_tasks(db, self._protocol_run_name)
        for scheduled_task in new_scheduled_tasks:
            if scheduled_task.name not in self._current_task_submissions:
                await self._execute_task(db, scheduled_task)

    async def _execute_task(self, db: AsyncDbSession, scheduled_task: ScheduledTask) -> None:
        """Execute a single task."""
        task = self._protocol_graph.get_task(scheduled_task.name)
        task = await self._task_input_resolver.resolve_task_inputs(db, self._protocol_run_name, task)

        # Use devices and resources from scheduled_task (already allocated by scheduler)
        task.devices = scheduled_task.devices
        task.resources = scheduled_task.resources

        task_submission = TaskSubmission.from_def(task, self._protocol_run_name)
        task_submission.priority = self._protocol_run_submission.priority

        self._task_output_futures[scheduled_task.name] = asyncio.create_task(
            self._task_executor.request_task_execution(task_submission, scheduled_task)
        )
        self._current_task_submissions[scheduled_task.name] = task_submission

    def _validate_parameters(self, parameters: dict[str, dict[str, Any]]) -> None:
        """Validate that all required parameters are provided."""
        required_params = self._get_required_parameters()
        provided_params = {
            f"{task_name}.{param_name}" for task_name, params in parameters.items() for param_name in params
        }

        missing_params = required_params - provided_params

        if missing_params:
            raise EosProtocolRunExecutionError(f"Missing values for parameters: {missing_params}")

    def _get_required_parameters(self) -> set[str]:
        """Get a set of all required parameters in the protocol graph."""
        return {
            f"{task_name}.{param_name}"
            for task_name in self._protocol_graph.get_tasks()
            for param_name, param_value in self._protocol_graph.get_task(task_name).parameters.items()
            if validation_utils.is_dynamic_parameter(param_value) or param_value is None
        }

    @property
    def protocol_run_submission(self) -> ProtocolRunSubmission:
        return self._protocol_run_submission
