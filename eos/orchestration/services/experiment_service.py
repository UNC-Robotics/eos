import asyncio
import traceback

from eos.configuration.configuration_manager import ConfigurationManager
from eos.experiments.entities.experiment import Experiment, ExperimentStatus, ExperimentSubmission
from eos.experiments.exceptions import EosExperimentExecutionError
from eos.experiments.experiment_executor_factory import ExperimentExecutorFactory
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.orchestration.exceptions import EosExperimentDoesNotExistError
from eos.orchestration.work_signal import WorkSignal
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.experiments.experiment_executor import ExperimentExecutor
from eos.utils.di.di_container import inject


class ExperimentService:
    """
    Top-level experiment functionality integration.
    Exposes an interface for submission, monitoring and cancellation of experiments.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        experiment_manager: ExperimentManager,
        experiment_executor_factory: ExperimentExecutorFactory,
        db_interface: AbstractSqlDbInterface,
        work_signal: WorkSignal,
    ):
        self._configuration_manager = configuration_manager
        self._experiment_manager = experiment_manager
        self._experiment_executor_factory = experiment_executor_factory
        self._db_interface = db_interface
        self._work_signal = work_signal

        self._experiment_submission_lock = asyncio.Lock()
        self._submitted_experiments: dict[str, ExperimentExecutor] = {}
        self._experiment_cancellation_queue = asyncio.Queue(maxsize=100)

    async def get_experiment(self, db: AsyncDbSession, experiment_name: str) -> Experiment | None:
        """Get an experiment by its unique identifier."""
        return await self._experiment_manager.get_experiment(db, experiment_name)

    async def submit_experiment(
        self,
        db: AsyncDbSession,
        experiment_submission: ExperimentSubmission,
    ) -> None:
        """Submit a new experiment for execution. The experiment will be executed asynchronously."""
        experiment_name = experiment_submission.name
        experiment_type = experiment_submission.type

        self._validate_experiment_type(experiment_type)

        async with self._experiment_submission_lock:
            if experiment_name in self._submitted_experiments:
                log.warning(f"Experiment '{experiment_name}' is already submitted. Ignoring new submission.")
                return

            experiment_executor = self._experiment_executor_factory.create(experiment_submission)

            try:
                await experiment_executor.start_experiment(db)
                self._submitted_experiments[experiment_name] = experiment_executor
                self._work_signal.signal()
            except EosExperimentExecutionError:
                log.error(f"Failed to submit experiment '{experiment_name}': {traceback.format_exc()}")
                self._submitted_experiments.pop(experiment_name, None)
                raise

    async def cancel_experiment(self, experiment_name: str) -> None:
        """
        Cancel an experiment that is currently being executed.

        :param experiment_name: The unique name of the experiment.
        """
        if experiment_name in self._submitted_experiments:
            await self._experiment_cancellation_queue.put(experiment_name)

    async def fail_running_experiments(self, db: AsyncDbSession) -> None:
        """Fail all running experiments."""
        running_experiments = await self._experiment_manager.get_experiments(db, status=ExperimentStatus.RUNNING.value)

        for experiment in running_experiments:
            await self._experiment_manager.fail_experiment(db, experiment.name)

        if running_experiments:
            log.warning(
                "All running experiments have been marked as failed. Please review the state of the system and "
                "re-submit with resume=True."
            )

    async def get_experiment_types(self) -> list[str]:
        """Get a list of all experiment types that are defined in the configuration."""
        return list(self._configuration_manager.experiments.keys())

    async def process_experiments(self) -> None:
        """Process experiments in priority order (higher priority first)."""
        if not self._submitted_experiments:
            return

        completed_experiments = []
        failed_experiments = []

        # Process experiments in priority order
        sorted_experiments = self._get_sorted_experiments()
        for experiment_name, experiment_executor in sorted_experiments:
            async with self._db_interface.get_async_session() as db:
                try:
                    completed = await experiment_executor.progress_experiment(db)

                    if completed:
                        completed_experiments.append(experiment_name)
                except EosExperimentExecutionError:
                    log.error(f"Error in experiment '{experiment_name}': {traceback.format_exc()}")
                    failed_experiments.append(experiment_name)
                except Exception:
                    log.error(f"Unexpected error in experiment '{experiment_name}': {traceback.format_exc()}")
                    failed_experiments.append(experiment_name)

        # Clean up completed and failed experiments
        for experiment_name in completed_experiments:
            del self._submitted_experiments[experiment_name]

        for experiment_name in failed_experiments:
            log.error(f"Failed experiment '{experiment_name}'.")
            del self._submitted_experiments[experiment_name]

    def _get_sorted_experiments(self) -> list[tuple[str, ExperimentExecutor]]:
        experiment_priorities = {}
        for exp_name, executor in self._submitted_experiments.items():
            experiment_priorities[exp_name] = executor.experiment_submission.priority

        return sorted(self._submitted_experiments.items(), key=lambda x: experiment_priorities[x[0]], reverse=True)

    async def process_experiment_cancellations(self) -> None:
        """Try to cancel all experiments that are queued for cancellation."""
        experiment_names = []
        while not self._experiment_cancellation_queue.empty():
            experiment_names.append(await self._experiment_cancellation_queue.get())

        if not experiment_names:
            return

        log.warning(f"Attempting to cancel experiments: {experiment_names}")

        async def cancel(exp_name: str) -> None:
            await self._submitted_experiments[exp_name].cancel_experiment()

        cancellation_tasks = [cancel(exp_name) for exp_name in experiment_names]
        results = await asyncio.gather(*cancellation_tasks, return_exceptions=True)

        for exp_name, result in zip(experiment_names, results, strict=True):
            if isinstance(result, Exception):
                log.error(f"Error cancelling experiment '{exp_name}': {result}")
            del self._submitted_experiments[exp_name]

        log.warning(f"Cancelled experiments: {experiment_names}")

    def _validate_experiment_type(self, experiment_type: str) -> None:
        if experiment_type not in self._configuration_manager.experiments:
            error_msg = f"Cannot submit experiment of type '{experiment_type}' as it does not exist."
            log.error(error_msg)
            raise EosExperimentDoesNotExistError(error_msg)

    @property
    def submitted_experiments(self) -> dict[str, ExperimentExecutor]:
        return self._submitted_experiments
