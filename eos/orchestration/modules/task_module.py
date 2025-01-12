from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_spec import TaskSpecConfig
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.tasks.entities.task import Task, TaskStatus, TaskDefinition
from eos.tasks.exceptions import EosTaskCancellationError
from eos.tasks.on_demand_task_executor import OnDemandTaskExecutor
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject_all


class TaskModule:
    """
    Top-level task functionality integration.
    Exposes an interface for submission, monitoring, and cancellation of tasks.
    """

    @inject_all
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

    async def get_task(self, db: AsyncDbSession, experiment_id: str, task_id: str) -> Task:
        """
        Get a task by its unique identifier.

        :param db: The database session.
        :param experiment_id: The unique identifier of the experiment.
        :param task_id: The unique identifier of the task.
        :return: The task entity.
        """
        return await self._task_manager.get_task(db, experiment_id, task_id)

    async def submit_task(
        self,
        db: AsyncDbSession,
        task_definition: TaskDefinition,
    ) -> None:
        """
        Submit a new task for execution.

        :param db: The database session.
        :param task_definition: The task definition.
        :return: The output of the task.
        """
        await self._on_demand_task_executor.submit_task(db, task_definition)

    async def cancel_task(self, task_id: str, experiment_id: str | None = None) -> None:
        """
        Cancel a task that is currently being executed.

        :param task_id: The unique identifier of the task.
        :param experiment_id: The unique identifier of the experiment.
        """
        try:
            if experiment_id is None:
                await self._on_demand_task_executor.cancel_task(task_id)
            else:
                await self._task_executor.cancel_task(experiment_id, task_id)
        except EosTaskCancellationError:
            log.error(f"Failed to cancel task '{task_id}'.")

    async def fail_running_tasks(self, db: AsyncDbSession) -> None:
        """Fail all running tasks."""
        running_tasks = await self._task_manager.get_tasks(db, status=TaskStatus.RUNNING.value)
        for task in running_tasks:
            await self._task_manager.fail_task(db, task.experiment_id, task.id)
            log.warning(f"EXP '{task.experiment_id}' - Failed task '{task.id}'.")

        if running_tasks:
            log.warning("All running tasks have been marked as failed. Please review the state of the system.")

    async def get_task_types(self) -> list[str]:
        """Get a list of all task types that are defined in the configuration."""
        return [task.type for task in self._configuration_manager.task_specs.get_all_specs().values()]

    async def get_task_spec(self, task_type: str) -> TaskSpecConfig | None:
        """Get the task specification for a given task type."""
        task_spec = self._configuration_manager.task_specs.get_spec_by_type(task_type)
        if not task_spec:
            log.error(f"Task type '{task_type}' does not exist.")

        return task_spec

    async def process_on_demand_tasks(self) -> None:
        """Try to make progress on all on-demand tasks."""
        await self._on_demand_task_executor.process_tasks()
