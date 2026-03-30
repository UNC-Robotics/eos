import asyncio
import traceback

from eos.configuration.configuration_manager import ConfigurationManager
from eos.protocols.entities.protocol_run import ProtocolRun, ProtocolRunStatus, ProtocolRunSubmission
from eos.protocols.exceptions import EosProtocolRunExecutionError
from eos.protocols.protocol_executor_factory import ProtocolExecutorFactory
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.logging.logger import log
from eos.orchestration.exceptions import EosProtocolRunDoesNotExistError
from eos.orchestration.work_signal import WorkSignal
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.protocols.protocol_executor import ProtocolExecutor
from eos.utils.di.di_container import inject


class ProtocolService:
    """
    Top-level protocol run functionality integration.
    Exposes an interface for submission, monitoring and cancellation of protocol runs.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        protocol_run_manager: ProtocolRunManager,
        protocol_executor_factory: ProtocolExecutorFactory,
        db_interface: AbstractSqlDbInterface,
        work_signal: WorkSignal,
    ):
        self._configuration_manager = configuration_manager
        self._protocol_run_manager = protocol_run_manager
        self._protocol_executor_factory = protocol_executor_factory
        self._db_interface = db_interface
        self._work_signal = work_signal

        self._protocol_run_submission_lock = asyncio.Lock()
        self._submitted_protocol_runs: dict[str, ProtocolExecutor] = {}
        self._protocol_run_cancellation_queue = asyncio.Queue(maxsize=100)

    async def get_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> ProtocolRun | None:
        """Get a protocol run by its unique identifier."""
        return await self._protocol_run_manager.get_protocol_run(db, protocol_run_name)

    async def submit_protocol_run(
        self,
        db: AsyncDbSession,
        protocol_run_submission: ProtocolRunSubmission,
    ) -> None:
        """Submit a new protocol run for execution. The protocol run will be executed asynchronously."""
        protocol_run_name = protocol_run_submission.name
        protocol_type = protocol_run_submission.type

        self._validate_protocol(protocol_type)

        async with self._protocol_run_submission_lock:
            if protocol_run_name in self._submitted_protocol_runs:
                log.warning(f"ProtocolRun '{protocol_run_name}' is already submitted. Ignoring new submission.")
                return

            protocol_executor = self._protocol_executor_factory.create(protocol_run_submission)

            try:
                await protocol_executor.start_protocol_run(db)
                await db.commit()
                self._submitted_protocol_runs[protocol_run_name] = protocol_executor
                self._work_signal.signal()
            except EosProtocolRunExecutionError:
                log.error(f"Failed to submit protocol run '{protocol_run_name}': {traceback.format_exc()}")
                self._submitted_protocol_runs.pop(protocol_run_name, None)
                raise

    async def cancel_protocol_run(self, protocol_run_name: str) -> None:
        """
        Cancel a protocol run that is currently being executed.

        :param protocol_run_name: The unique name of the protocol run.
        """
        if protocol_run_name in self._submitted_protocol_runs:
            await self._protocol_run_cancellation_queue.put(protocol_run_name)

    async def fail_running_protocol_runs(self, db: AsyncDbSession) -> None:
        """Fail all running protocols."""
        running_protocol_runs = await self._protocol_run_manager.get_protocol_runs(
            db, status=ProtocolRunStatus.RUNNING.value
        )
        if not running_protocol_runs:
            return

        names = [r.name for r in running_protocol_runs]
        await self._protocol_run_manager.fail_protocol_runs_batch(
            db, names, error_message="ProtocolRun was running when the orchestrator restarted"
        )
        log.warning(
            "All running protocols have been marked as failed. Please review the state of the system and "
            "re-submit with resume=True."
        )

    async def get_protocol_types(self) -> list[str]:
        """Get a list of all protocol types that are defined in the configuration."""
        return list(self._configuration_manager.protocols.keys())

    async def process_protocol_runs(self) -> None:
        """Process protocols in priority order (higher priority first)."""
        if not self._submitted_protocol_runs:
            return

        completed_protocol_runs = []
        failed_protocol_runs = []

        # Process protocol runs in priority order
        sorted_protocol_runs = self._get_sorted_protocol_runs()
        for protocol_run_name, protocol_executor in sorted_protocol_runs:
            async with self._db_interface.get_async_session() as db:
                try:
                    completed = await protocol_executor.progress_protocol_run(db)

                    if completed:
                        completed_protocol_runs.append(protocol_run_name)
                except EosProtocolRunExecutionError:
                    log.error(f"Error in protocol run '{protocol_run_name}': {traceback.format_exc()}")
                    failed_protocol_runs.append(protocol_run_name)
                except Exception:
                    log.error(f"Unexpected error in protocol run '{protocol_run_name}': {traceback.format_exc()}")
                    failed_protocol_runs.append(protocol_run_name)

        # Clean up completed and failed protocol runs
        for protocol_run_name in completed_protocol_runs:
            del self._submitted_protocol_runs[protocol_run_name]

        for protocol_run_name in failed_protocol_runs:
            log.error(f"Failed protocol run '{protocol_run_name}'.")
            del self._submitted_protocol_runs[protocol_run_name]

    def _get_sorted_protocol_runs(self) -> list[tuple[str, ProtocolExecutor]]:
        protocol_run_priorities = {}
        for run_name, executor in self._submitted_protocol_runs.items():
            protocol_run_priorities[run_name] = executor.protocol_run_submission.priority

        return sorted(self._submitted_protocol_runs.items(), key=lambda x: protocol_run_priorities[x[0]], reverse=True)

    async def process_protocol_run_cancellations(self) -> None:
        """Try to cancel all protocols that are queued for cancellation."""
        protocol_run_names = []
        while not self._protocol_run_cancellation_queue.empty():
            protocol_run_names.append(await self._protocol_run_cancellation_queue.get())

        if not protocol_run_names:
            return

        log.warning(f"Attempting to cancel protocols: {protocol_run_names}")

        async def cancel(run_name: str) -> None:
            await self._submitted_protocol_runs[run_name].cancel_protocol_run()

        cancellation_tasks = [cancel(run_name) for run_name in protocol_run_names]
        results = await asyncio.gather(*cancellation_tasks, return_exceptions=True)

        for run_name, result in zip(protocol_run_names, results, strict=True):
            if isinstance(result, Exception):
                log.error(f"Error cancelling protocol run '{run_name}': {result}")
            del self._submitted_protocol_runs[run_name]

        log.warning(f"Cancelled protocols: {protocol_run_names}")

    def _validate_protocol(self, protocol_type: str) -> None:
        if protocol_type not in self._configuration_manager.protocols:
            error_msg = f"Cannot submit protocol run of type '{protocol_type}' as it does not exist."
            log.error(error_msg)
            raise EosProtocolRunDoesNotExistError(error_msg)

    @property
    def submitted_protocol_runs(self) -> dict[str, ProtocolExecutor]:
        return self._submitted_protocol_runs
