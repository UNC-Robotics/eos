import asyncio
from typing import Any

from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph
from eos.configuration.validation import validation_utils
from eos.containers.container_manager import ContainerManager
from eos.experiments.entities.experiment import ExperimentStatus, Experiment, ExperimentDefinition
from eos.experiments.exceptions import (
    EosExperimentExecutionError,
    EosExperimentTaskExecutionError,
    EosExperimentCancellationError,
)
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.entities.task import TaskOutput, TaskDefinition
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
        container_manager: ContainerManager,
        task_executor: TaskExecutor,
        scheduler: AbstractScheduler,
    ):
        self._experiment_definition = experiment_definition
        self._experiment_id = experiment_definition.id
        self._experiment_type = experiment_definition.type
        self._experiment_graph = experiment_graph

        self._experiment_manager = experiment_manager
        self._task_manager = task_manager
        self._container_manager = container_manager
        self._task_executor = task_executor
        self._scheduler = scheduler
        self._task_input_resolver = TaskInputResolver(task_manager, experiment_manager)

        self._current_task_definitions: dict[str, TaskDefinition] = {}
        self._task_output_futures: dict[str, asyncio.Task] = {}
        self._experiment_status = None

    async def start_experiment(self) -> None:
        """
        Start the experiment and register the executor with the scheduler.
        """
        experiment = await self._experiment_manager.get_experiment(self._experiment_id)
        if experiment:
            await self._handle_existing_experiment(experiment)
        else:
            await self._create_new_experiment()

        self._scheduler.register_experiment(
            experiment_id=self._experiment_id,
            experiment_type=self._experiment_type,
            experiment_graph=self._experiment_graph,
        )

        await self._experiment_manager.start_experiment(self._experiment_id)
        self._experiment_status = ExperimentStatus.RUNNING

        log.info(
            f"{'Resumed' if self._experiment_definition.resume else 'Started'} experiment '{self._experiment_id}'."
        )

    async def _handle_existing_experiment(self, experiment: Experiment) -> None:
        """
        Handle cases when the experiment already exists.
        """
        self._experiment_status = experiment.status

        if not self._experiment_definition.resume:

            def _raise_error(status: str) -> None:
                raise EosExperimentExecutionError(
                    f"Cannot start experiment '{self._experiment_id}' as it already exists and is '{status}'. "
                    f"Please create a new experiment or re-submit with 'resume=True'."
                )

            status_handlers = {
                ExperimentStatus.COMPLETED: lambda: _raise_error("completed"),
                ExperimentStatus.SUSPENDED: lambda: _raise_error("suspended"),
                ExperimentStatus.CANCELLED: lambda: _raise_error("cancelled"),
                ExperimentStatus.FAILED: lambda: _raise_error("failed"),
            }
            status_handlers.get(self._experiment_status, lambda: None)()
        else:
            await self._resume_experiment()

    async def cancel_experiment(self) -> None:
        """
        Cancel the experiment.
        """
        experiment = await self._experiment_manager.get_experiment(self._experiment_id)
        if not experiment or experiment.status != ExperimentStatus.RUNNING:
            raise EosExperimentCancellationError(
                f"Cannot cancel experiment '{self._experiment_id}' with status '{experiment.status}'. "
                f"It must be running."
            )

        log.warning(f"Cancelling experiment '{self._experiment_id}'...")
        self._experiment_status = ExperimentStatus.CANCELLED

        await asyncio.gather(
            self._experiment_manager.cancel_experiment(self._experiment_id),
            self._scheduler.unregister_experiment(self._experiment_id),
            self._cancel_running_tasks(),
        )
        log.warning(f"Cancelled experiment '{self._experiment_id}'.")

    async def progress_experiment(self) -> bool:
        """
        Try to progress the experiment by executing tasks.

        :return: True if the experiment has been completed, False otherwise.
        """
        try:
            if self._experiment_status != ExperimentStatus.RUNNING:
                return self._experiment_status == ExperimentStatus.CANCELLED

            if await self._scheduler.is_experiment_completed(self._experiment_id):
                await self._complete_experiment()
                return True

            await self._process_completed_tasks()
            await self._execute_tasks()

            return False
        except Exception as e:
            await self._fail_experiment()
            raise EosExperimentExecutionError(f"Error executing experiment '{self._experiment_id}'") from e

    async def _resume_experiment(self) -> None:
        """
        Resume an existing experiment.
        """
        await self._experiment_manager.delete_non_completed_tasks(self._experiment_id)
        log.info(f"Experiment '{self._experiment_id}' resumed.")

    async def _create_new_experiment(self) -> None:
        """
        Create a new experiment.
        """
        dynamic_parameters = self._experiment_definition.dynamic_parameters or {}
        self._validate_dynamic_parameters(dynamic_parameters)
        await self._experiment_manager.create_experiment(self._experiment_definition)

    async def _cancel_running_tasks(self) -> None:
        """
        Cancel all running tasks in the experiment.
        """
        cancellation_futures = [
            self._task_executor.request_task_cancellation(task_definition.experiment_id, task_definition.id)
            for task_definition in self._current_task_definitions.values()
        ]
        try:
            await asyncio.wait_for(asyncio.gather(*cancellation_futures), timeout=30)
        except EosTaskCancellationError as e:
            raise EosExperimentExecutionError(
                f"Error cancelling tasks of experiment {self._experiment_id}. Some tasks may not have been cancelled."
            ) from e
        except asyncio.TimeoutError as e:
            raise EosExperimentExecutionError(
                f"Timeout while cancelling experiment {self._experiment_id}. Some tasks may not have been cancelled."
            ) from e

    async def _complete_experiment(self) -> None:
        """
        Complete the experiment and clean up.
        """
        await asyncio.gather(
            self._scheduler.unregister_experiment(self._experiment_id),
            self._experiment_manager.complete_experiment(self._experiment_id),
        )
        self._experiment_status = ExperimentStatus.COMPLETED
        log.info(f"Completed experiment '{self._experiment_id}'.")

    async def _fail_experiment(self) -> None:
        """
        Fail the experiment.
        """
        await asyncio.gather(
            self._scheduler.unregister_experiment(self._experiment_id),
            self._experiment_manager.fail_experiment(self._experiment_id),
        )
        self._experiment_status = ExperimentStatus.FAILED

    async def _process_completed_tasks(self) -> None:
        """
        Process the output of completed tasks.
        """
        completed_tasks = [task_id for task_id, future in self._task_output_futures.items() if future.done()]
        for task_id in completed_tasks:
            await self._process_task_output(task_id)

    async def _process_task_output(self, task_id: str) -> None:
        """
        Process the output of a single completed task.
        """
        try:
            result = self._task_output_futures[task_id].result()
            if result:
                output_parameters, output_containers, output_files = result
                await self._update_containers(output_containers)
                await self._add_task_output(task_id, output_parameters, output_containers, output_files)
            await self._task_manager.complete_task(self._experiment_id, task_id)
            log.info(f"EXP '{self._experiment_id}' - Completed task '{task_id}'.")
        except EosTaskExecutionError as e:
            raise EosExperimentTaskExecutionError(
                f"Error executing task '{task_id}' of experiment '{self._experiment_id}'"
            ) from e
        finally:
            del self._task_output_futures[task_id]
            del self._current_task_definitions[task_id]

    async def _update_containers(self, output_containers: dict[str, Any]) -> None:
        """
        Update containers with task output.
        """
        for container in output_containers.values():
            await self._container_manager.update_container(container)

    async def _add_task_output(
        self,
        task_id: str,
        output_parameters: dict[str, Any],
        output_containers: dict[str, Any],
        output_files: dict[str, Any],
    ) -> None:
        """
        Add task output to the task manager.
        """
        task_output = TaskOutput(
            parameters=output_parameters,
            containers=output_containers,
            file_names=list(output_files.keys()),
        )
        for file_name, file_data in output_files.items():
            self._task_manager.add_task_output_file(self._experiment_id, task_id, file_name, file_data)
        await self._task_manager.add_task_output(self._experiment_id, task_id, task_output)

    async def _execute_tasks(self) -> None:
        """
        Request and execute new tasks from the scheduler.
        """
        new_scheduled_tasks = await self._scheduler.request_tasks(self._experiment_id)
        for scheduled_task in new_scheduled_tasks:
            if scheduled_task.id not in self._current_task_definitions:
                await self._execute_task(scheduled_task)

    async def _execute_task(self, scheduled_task: ScheduledTask) -> None:
        """
        Execute a single task.
        """
        task_config = self._experiment_graph.get_task_config(scheduled_task.id)
        task_config = await self._task_input_resolver.resolve_task_inputs(self._experiment_id, task_config)
        task_definition = TaskDefinition.from_config(task_config, self._experiment_id)

        self._task_output_futures[scheduled_task.id] = asyncio.create_task(
            self._task_executor.request_task_execution(task_definition, scheduled_task)
        )
        self._current_task_definitions[scheduled_task.id] = task_definition

    def _validate_dynamic_parameters(self, dynamic_parameters: dict[str, dict[str, Any]]) -> None:
        """
        Validate that all required dynamic parameters are provided and there are no surplus parameters.
        """
        required_params = self._get_required_dynamic_parameters()
        provided_params = {
            f"{task_id}.{param_name}" for task_id, params in dynamic_parameters.items() for param_name in params
        }

        missing_params = required_params - provided_params
        unexpected_params = provided_params - required_params

        if missing_params:
            raise EosExperimentExecutionError(f"Missing values for dynamic parameters: {missing_params}")
        if unexpected_params:
            raise EosExperimentExecutionError(f"Unexpected dynamic parameters provided: {unexpected_params}")

    def _get_required_dynamic_parameters(self) -> set[str]:
        """
        Get a set of all required dynamic parameters in the experiment graph.
        """
        return {
            f"{task_id}.{param_name}"
            for task_id in self._experiment_graph.get_tasks()
            for param_name, param_value in self._experiment_graph.get_task_config(task_id).parameters.items()
            if validation_utils.is_dynamic_parameter(param_value)
        }
