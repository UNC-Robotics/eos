import asyncio
import traceback

from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import TaskDefinition
from eos.tasks.exceptions import EosTaskExecutionError
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject_all


class OnDemandTaskExecutor:
    """
    Executor for on-demand tasks (not part of an experiment or campaign).
    """

    @inject_all
    def __init__(
        self,
        task_executor: TaskExecutor,
        task_manager: TaskManager,
    ):
        self._task_executor = task_executor
        self._task_manager = task_manager

        self._task_futures: dict[str, asyncio.Task] = {}

        log.debug("On-demand task executor initialized.")

    async def submit_task(self, db: AsyncDbSession, task_definition: TaskDefinition) -> None:
        """Submit an on-demand task for execution."""
        if await self._task_manager.get_task(db, None, task_definition.id):
            raise EosTaskExecutionError(f"Cannot submit duplicate on-demand task '{task_definition.id}'.")

        self._task_futures[task_definition.id] = asyncio.create_task(
            self._task_executor.request_task_execution(task_definition)
        )
        log.info(f"Submitted on-demand task '{task_definition.id}'.")

    async def cancel_task(self, task_id: str) -> None:
        """Cancel an on-demand task."""
        if task_id not in self._task_futures:
            raise EosTaskExecutionError(f"Cannot cancel non-existent on-demand task '{task_id}'.")

        await self._task_executor.cancel_task(None, task_id)
        self._task_futures.pop(task_id, None)
        log.warning(f"Cancelled on-demand task '{task_id}'.")

    async def process_tasks(self) -> None:
        """Process the on-demand tasks that have been submitted."""
        completed_tasks = []
        for task_id, future in self._task_futures.items():
            if not future.done():
                continue

            try:
                await future  # Just check for exceptions
            except asyncio.CancelledError:
                log.info(f"On-demand task '{task_id}' was cancelled.")
            except Exception:
                log.error(f"Failed on-demand task '{task_id}': {traceback.format_exc()}")
            finally:
                completed_tasks.append(task_id)

        for task_id in completed_tasks:
            del self._task_futures[task_id]

    @property
    def has_work(self) -> bool:
        """Check if there are any on-demand tasks that need processing."""
        return bool(self._task_futures)
