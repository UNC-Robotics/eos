import traceback

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.tasks.entities.task import Task, TaskStatus, TaskSubmission
from eos.tasks.exceptions import EosTaskCancellationError, EosTaskExecutionError
from eos.tasks.on_demand_task_executor import OnDemandTaskExecutor
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
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
        on_demand_task_executor: OnDemandTaskExecutor,
        db_interface: AbstractSqlDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._task_manager = task_manager
        self._task_executor = task_executor
        self._on_demand_task_executor = on_demand_task_executor
        self._db_interface = db_interface

    async def get_task(self, db: AsyncDbSession, experiment_name: str, task_name: str) -> Task:
        """
        Get a task by its unique name.

        :param db: The database session.
        :param experiment_name: The unique name of the experiment.
        :param task_name: The unique name of the task.
        :return: The task entity.
        """
        return await self._task_manager.get_task(db, experiment_name, task_name)

    async def submit_task(
        self,
        db: AsyncDbSession,
        task_submission: TaskSubmission,
    ) -> None:
        """
        Submit a new task for execution.

        :param db: The database session.
        :param task_submission: The task submission.
        :return: The output of the task.
        """
        try:
            await self._on_demand_task_executor.submit_task(db, task_submission)
        except EosTaskExecutionError:
            log.error(f"Failed to submit task '{task_submission.name}': {traceback.format_exc()}")
            raise

    async def cancel_task(self, task_name: str, experiment_name: str | None = None) -> None:
        """
        Cancel a task that is currently being executed.

        :param task_name: The unique name of the task.
        :param experiment_name: The unique name of the experiment.
        """
        try:
            if experiment_name is None:
                await self._on_demand_task_executor.cancel_task(task_name)
            else:
                await self._task_executor.cancel_task(experiment_name, task_name)
        except EosTaskCancellationError:
            log.error(f"Failed to cancel task '{task_name}'.")
            raise

    async def fail_running_tasks(self, db: AsyncDbSession) -> None:
        """Fail all running tasks."""
        running_tasks = await self._task_manager.get_tasks(db, status=TaskStatus.RUNNING.value)
        for task in running_tasks:
            await self._task_manager.fail_task(db, task.experiment_name, task.name)
            log.warning(f"EXP '{task.experiment_name}' - Failed task '{task.name}'.")

        if running_tasks:
            log.warning("All running tasks have been marked as failed. Please review the state of the system.")

    async def get_task_types(self) -> list[str]:
        """Get a list of all task types that are defined in the configuration."""
        return [task.type for task in self._configuration_manager.task_specs.get_all_specs().values()]

    async def process_on_demand_tasks(self) -> None:
        """Try to make progress on all on-demand tasks."""
        await self._on_demand_task_executor.process_tasks()
