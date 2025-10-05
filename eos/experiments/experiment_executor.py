import asyncio
from typing import Any

from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph
from eos.configuration.validation import validation_utils
from eos.experiments.entities.experiment import ExperimentStatus, Experiment, ExperimentDefinition
from eos.experiments.exceptions import (
    EosExperimentExecutionError,
    EosExperimentTaskExecutionError,
    EosExperimentCancellationError,
)
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.entities.task import TaskDefinition
from eos.tasks.exceptions import EosTaskExecutionError, EosTaskCancellationError
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_input_resolver import TaskInputResolver
from eos.tasks.task_manager import TaskManager


class ExperimentExecutor:
    """Responsible for executing all the tasks of a single experiment."""

    def __init__(
        self,
        experiment_definition: ExperimentDefinition,
        experiment_graph: ExperimentGraph,
        experiment_manager: ExperimentManager,
        task_manager: TaskManager,
        task_executor: TaskExecutor,
        scheduler: AbstractScheduler,
        db_interface: AbstractSqlDbInterface,
    ):
        self._experiment_definition = experiment_definition
        self._experiment_name = experiment_definition.name
        self._experiment_type = experiment_definition.type
        self._experiment_graph = experiment_graph

        self._experiment_manager = experiment_manager
        self._task_manager = task_manager
        self._task_executor = task_executor
        self._scheduler = scheduler
        self._db_interface = db_interface
        self._task_input_resolver = TaskInputResolver(task_manager, experiment_manager)

        self._current_task_definitions: dict[str, TaskDefinition] = {}
        self._task_output_futures: dict[str, asyncio.Task] = {}
        self._experiment_status = None

    async def start_experiment(self, db: AsyncDbSession) -> None:
        """Start the experiment and register the executor with the scheduler."""
        experiment = await self._experiment_manager.get_experiment(db, self._experiment_name)
        if experiment:
            await self._handle_existing_experiment(db, experiment)
        else:
            await self._create_new_experiment(db)

        await self._scheduler.register_experiment(
            experiment_name=self._experiment_name,
            experiment_type=self._experiment_type,
            experiment_graph=self._experiment_graph,
        )

        await self._experiment_manager.start_experiment(db, self._experiment_name)
        self._experiment_status = ExperimentStatus.RUNNING

        log.info(
            f"{'Resumed' if self._experiment_definition.resume else 'Started'} experiment '{self._experiment_name}'."
        )

    async def _handle_existing_experiment(self, db: AsyncDbSession, experiment: Experiment) -> None:
        """Handle cases when the experiment already exists."""
        self._experiment_status = experiment.status

        if not self._experiment_definition.resume:
            if self._experiment_status in (
                ExperimentStatus.COMPLETED,
                ExperimentStatus.SUSPENDED,
                ExperimentStatus.CANCELLED,
                ExperimentStatus.FAILED,
            ):
                raise EosExperimentExecutionError(
                    f"Cannot start experiment '{self._experiment_name}' as it already exists and is "
                    f"'{self._experiment_status.value}'. Please create a new experiment or re-submit with "
                    f"'resume=True'."
                )
        else:
            await self._resume_experiment(db)

    async def cancel_experiment(self) -> None:
        """Cancel the experiment."""
        async with self._db_interface.get_async_session() as db:
            experiment = await self._experiment_manager.get_experiment(db, self._experiment_name)
            if not experiment or experiment.status != ExperimentStatus.RUNNING:
                raise EosExperimentCancellationError(
                    f"Cannot cancel experiment '{self._experiment_name}' with status '{experiment.status}'. "
                    f"It must be running."
                )

            log.warning(f"Cancelling experiment '{self._experiment_name}'...")
            self._experiment_status = ExperimentStatus.CANCELLED

            await self._experiment_manager.cancel_experiment(db, self._experiment_name)
            await self._scheduler.unregister_experiment(db, self._experiment_name)

        await self._cancel_running_tasks()

        log.warning(f"Cancelled experiment '{self._experiment_name}'.")

    async def progress_experiment(self, db: AsyncDbSession) -> bool:
        """
        Try to progress the experiment by executing tasks.

        :return: True if the experiment has been completed, False otherwise.
        """
        try:
            if self._experiment_status != ExperimentStatus.RUNNING:
                return self._experiment_status == ExperimentStatus.CANCELLED

            if await self._scheduler.is_experiment_completed(db, self._experiment_name):
                await self._complete_experiment(db)
                return True

            await self._process_completed_tasks(db)
            await db.commit()
            await self._execute_tasks(db)

            return False
        except Exception as e:
            await self._fail_experiment(db)
            raise EosExperimentExecutionError(f"Error executing experiment '{self._experiment_name}'") from e

    async def _resume_experiment(self, db: AsyncDbSession) -> None:
        """Resume an existing experiment."""
        await self._experiment_manager.delete_non_completed_tasks(db, self._experiment_name)
        log.info(f"Experiment '{self._experiment_name}' resumed.")

    async def _create_new_experiment(self, db: AsyncDbSession) -> None:
        """
        Create a new experiment.
        """
        parameters = self._experiment_definition.parameters or {}
        self._validate_parameters(parameters)
        await self._experiment_manager.create_experiment(db, self._experiment_definition)

    async def _cancel_running_tasks(self) -> None:
        """Cancel all running tasks in the experiment."""
        cancellation_tasks = [
            self._task_executor.cancel_task(task_definition.experiment_name, task_definition.name)
            for task_definition in self._current_task_definitions.values()
        ]
        try:
            await asyncio.gather(*cancellation_tasks, return_exceptions=True)

        except EosTaskCancellationError as e:
            raise EosExperimentExecutionError(
                f"Error cancelling tasks of experiment {self._experiment_name}. Some tasks may not have been cancelled."
            ) from e
        except asyncio.TimeoutError as e:
            raise EosExperimentExecutionError(
                f"Timeout while cancelling experiment {self._experiment_name}. Some tasks may not have been cancelled."
            ) from e

    async def _complete_experiment(self, db: AsyncDbSession) -> None:
        """Complete the experiment and clean up."""
        await self._scheduler.unregister_experiment(db, self._experiment_name)
        await self._experiment_manager.complete_experiment(db, self._experiment_name)
        self._experiment_status = ExperimentStatus.COMPLETED
        log.info(f"Completed experiment '{self._experiment_name}'.")

    async def _fail_experiment(self, db: AsyncDbSession) -> None:
        """Fail the experiment and cancel any running tasks."""
        await self._scheduler.unregister_experiment(db, self._experiment_name)
        await self._experiment_manager.fail_experiment(db, self._experiment_name)
        self._experiment_status = ExperimentStatus.FAILED

        # Ensure any running tasks are cancelled to avoid orphan work
        try:
            await self._cancel_running_tasks()
        finally:
            log.warning(f"Failed experiment '{self._experiment_name}'. All running tasks cancelled.")

    async def _process_completed_tasks(self, db: AsyncDbSession) -> None:
        """Process the output of completed tasks."""
        completed_tasks = [task_name for task_name, future in self._task_output_futures.items() if future.done()]
        for task_name in completed_tasks:
            try:
                self._task_output_futures[task_name].result()  # Just check for exceptions
            except EosTaskExecutionError as e:
                raise EosExperimentTaskExecutionError(
                    f"Error executing task '{task_name}' of experiment '{self._experiment_name}'"
                ) from e
            finally:
                del self._task_output_futures[task_name]
                del self._current_task_definitions[task_name]

    async def _execute_tasks(self, db: AsyncDbSession) -> None:
        """Request and execute new tasks from the scheduler."""
        new_scheduled_tasks = await self._scheduler.request_tasks(db, self._experiment_name)
        for scheduled_task in new_scheduled_tasks:
            if scheduled_task.name not in self._current_task_definitions:
                await self._execute_task(db, scheduled_task)

    async def _execute_task(self, db: AsyncDbSession, scheduled_task: ScheduledTask) -> None:
        """Execute a single task."""
        task_config = self._experiment_graph.get_task_config(scheduled_task.name)
        task_config = await self._task_input_resolver.resolve_task_inputs(db, self._experiment_name, task_config)

        # Use devices and resources from scheduled_task (already allocated by scheduler)
        task_config.devices = scheduled_task.devices
        task_config.resources = scheduled_task.resources

        task_definition = TaskDefinition.from_config(task_config, self._experiment_name)
        task_definition.priority = self._experiment_definition.priority

        self._task_output_futures[scheduled_task.name] = asyncio.create_task(
            self._task_executor.request_task_execution(task_definition, scheduled_task)
        )
        self._current_task_definitions[scheduled_task.name] = task_definition

    def _validate_parameters(self, parameters: dict[str, dict[str, Any]]) -> None:
        """Validate that all required parameters are provided."""
        required_params = self._get_required_parameters()
        provided_params = {
            f"{task_name}.{param_name}" for task_name, params in parameters.items() for param_name in params
        }

        missing_params = required_params - provided_params

        if missing_params:
            raise EosExperimentExecutionError(f"Missing values for parameters: {missing_params}")

    def _get_required_parameters(self) -> set[str]:
        """Get a set of all required parameters in the experiment graph."""
        return {
            f"{task_name}.{param_name}"
            for task_name in self._experiment_graph.get_tasks()
            for param_name, param_value in self._experiment_graph.get_task_config(task_name).parameters.items()
            if validation_utils.is_dynamic_parameter(param_value) or param_value is None
        }

    @property
    def experiment_definition(self) -> ExperimentDefinition:
        return self._experiment_definition
