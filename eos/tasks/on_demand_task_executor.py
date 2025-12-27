import asyncio
import traceback

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import TaskSubmission
from eos.tasks.exceptions import EosTaskExecutionError
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject


class OnDemandTaskExecutor:
    """
    Executor for on-demand tasks (not part of an experiment or campaign).
    """

    @inject
    def __init__(
        self,
        task_executor: TaskExecutor,
        task_manager: TaskManager,
        configuration_manager: ConfigurationManager,
    ):
        self._task_executor = task_executor
        self._task_manager = task_manager
        self._configuration_manager = configuration_manager

        self._task_futures: dict[str, asyncio.Task] = {}

        log.debug("On-demand task executor initialized.")

    async def submit_task(self, db: AsyncDbSession, task_submission: TaskSubmission) -> None:
        """Submit an on-demand task for execution."""
        task_spec = self._configuration_manager.task_specs.get_spec_by_type(task_submission.type)
        if not task_spec:
            raise EosTaskExecutionError(f"Unknown task type '{task_submission.type}'.")

        if await self._task_manager.get_task(db, None, task_submission.name):
            raise EosTaskExecutionError(f"Cannot submit duplicate on-demand task '{task_submission.name}'.")

        self._task_futures[task_submission.name] = asyncio.create_task(
            self._task_executor.request_task_execution(task_submission)
        )
        log.info(f"Submitted on-demand task '{task_submission.name}'.")

    async def cancel_task(self, task_name: str) -> None:
        """Cancel an on-demand task."""
        if task_name not in self._task_futures:
            raise EosTaskExecutionError(f"Cannot cancel non-existent on-demand task '{task_name}'.")

        await self._task_executor.cancel_task(None, task_name)
        self._task_futures.pop(task_name, None)
        log.warning(f"Cancelled on-demand task '{task_name}'.")

    async def process_tasks(self) -> None:
        """Process the on-demand tasks that have been submitted."""
        completed_tasks = []
        for task_name, future in self._task_futures.items():
            if not future.done():
                continue

            try:
                await future  # Just check for exceptions
            except asyncio.CancelledError:
                log.info(f"On-demand task '{task_name}' was cancelled.")
            except Exception:
                log.error(f"Failed on-demand task '{task_name}': {traceback.format_exc()}")
            finally:
                completed_tasks.append(task_name)

        for task_name in completed_tasks:
            del self._task_futures[task_name]

    @property
    def has_work(self) -> bool:
        """Check if there are any on-demand tasks that need processing."""
        return bool(self._task_futures)
