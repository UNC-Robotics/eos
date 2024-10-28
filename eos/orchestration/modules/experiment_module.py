import asyncio
import traceback
from typing import Any, TYPE_CHECKING

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.validation import validation_utils
from eos.experiments.entities.experiment import Experiment, ExperimentStatus, ExperimentDefinition
from eos.experiments.exceptions import EosExperimentExecutionError
from eos.experiments.experiment_executor_factory import ExperimentExecutorFactory
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.orchestration.exceptions import EosExperimentDoesNotExistError

if TYPE_CHECKING:
    from eos.experiments.experiment_executor import ExperimentExecutor


class ExperimentModule:
    """
    Top-level experiment functionality integration.
    Exposes an interface for submission, monitoring and cancellation of experiments.
    """

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        experiment_manager: ExperimentManager,
        experiment_executor_factory: ExperimentExecutorFactory,
    ):
        self._configuration_manager = configuration_manager
        self._experiment_manager = experiment_manager
        self._experiment_executor_factory = experiment_executor_factory

        self._experiment_submission_lock = asyncio.Lock()
        self._submitted_experiments: dict[str, ExperimentExecutor] = {}
        self._experiment_cancellation_queue = asyncio.Queue(maxsize=100)

    async def get_experiment(self, experiment_id: str) -> Experiment | None:
        """Get an experiment by its unique identifier."""
        return await self._experiment_manager.get_experiment(experiment_id)

    async def submit_experiment(
        self,
        experiment_definition: ExperimentDefinition,
    ) -> None:
        """Submit a new experiment for execution. The experiment will be executed asynchronously."""
        experiment_id = experiment_definition.id
        experiment_type = experiment_definition.type

        self._validate_experiment_type(experiment_type)

        async with self._experiment_submission_lock:
            if experiment_id in self._submitted_experiments:
                log.warning(f"Experiment '{experiment_id}' is already submitted. Ignoring new submission.")
                return

            experiment_executor = self._experiment_executor_factory.create(experiment_definition)

            try:
                await experiment_executor.start_experiment()
                self._submitted_experiments[experiment_id] = experiment_executor
            except EosExperimentExecutionError:
                log.error(f"Failed to submit experiment '{experiment_id}': {traceback.format_exc()}")
                del self._submitted_experiments[experiment_id]
                return

            log.info(f"Submitted experiment '{experiment_id}'.")

    async def cancel_experiment(self, experiment_id: str) -> None:
        """
        Cancel an experiment that is currently being executed.

        :param experiment_id: The unique identifier of the experiment.
        """
        if experiment_id in self._submitted_experiments:
            await self._experiment_cancellation_queue.put(experiment_id)

    async def fail_running_experiments(self) -> None:
        """Fail all running experiments."""
        running_experiments = await self._experiment_manager.get_experiments(status=ExperimentStatus.RUNNING.value)

        for experiment in running_experiments:
            await self._experiment_manager.fail_experiment(experiment.id)

        if running_experiments:
            log.warning(
                "All running experiments have been marked as failed. Please review the state of the system and "
                "re-submit with resume=True."
            )

    async def get_experiment_types(self) -> list[str]:
        """
        Get a list of all experiment types that are defined in the configuration.
        """
        return list(self._configuration_manager.experiments.keys())

    async def get_experiment_dynamic_params_template(self, experiment_type: str) -> dict[str, Any]:
        """
        Get the dynamic parameters template for a given experiment type.

        :param experiment_type: The type of the experiment.
        :return: The dynamic parameter template.
        """
        experiment_config = self._configuration_manager.experiments[experiment_type]
        dynamic_parameters = {}

        for task in experiment_config.tasks:
            task_dynamic_parameters = {
                name: "PLACEHOLDER"
                for name, value in task.parameters.items()
                if validation_utils.is_dynamic_parameter(value)
            }
            if task_dynamic_parameters:
                dynamic_parameters[task.id] = task_dynamic_parameters

        return dynamic_parameters

    async def process_experiments(self) -> None:
        """Try to make progress on all submitted experiments"""
        if not self._submitted_experiments:
            return

        completed_experiments = []
        failed_experiments = []

        for experiment_id, experiment_executor in self._submitted_experiments.items():
            try:
                completed = await experiment_executor.progress_experiment()

                if completed:
                    completed_experiments.append(experiment_id)
            except EosExperimentExecutionError:
                log.error(f"Error in experiment '{experiment_id}': {traceback.format_exc()}")
                failed_experiments.append(experiment_id)

        for experiment_id in completed_experiments:
            log.info(f"Completed experiment '{experiment_id}'.")
            del self._submitted_experiments[experiment_id]

        for experiment_id in failed_experiments:
            log.error(f"Failed experiment '{experiment_id}'.")
            del self._submitted_experiments[experiment_id]

    async def process_experiment_cancellations(self) -> None:
        """Try to cancel all experiments that are queued for cancellation."""
        experiment_ids = []
        while not self._experiment_cancellation_queue.empty():
            experiment_ids.append(await self._experiment_cancellation_queue.get())

        if not experiment_ids:
            return

        log.warning(f"Attempting to cancel experiments: {experiment_ids}")
        cancellation_tasks = [self._submitted_experiments[exp_id].cancel_experiment() for exp_id in experiment_ids]
        await asyncio.gather(*cancellation_tasks)

        for exp_id in experiment_ids:
            del self._submitted_experiments[exp_id]

        log.warning(f"Cancelled experiments: {experiment_ids}")

    def _validate_experiment_type(self, experiment_type: str) -> None:
        if experiment_type not in self._configuration_manager.experiments:
            log.error(f"Cannot submit experiment of type '{experiment_type}' as it does not exist.")
            raise EosExperimentDoesNotExistError
