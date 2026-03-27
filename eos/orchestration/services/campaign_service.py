import asyncio
import traceback
from typing import Any, TYPE_CHECKING

from eos.campaigns.campaign_executor import CampaignExecutor
from eos.campaigns.campaign_executor_factory import CampaignExecutorFactory
from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.campaigns.entities.campaign import Campaign, CampaignStatus, CampaignSubmission
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.orchestration.exceptions import EosProtocolRunDoesNotExistError
from eos.orchestration.work_signal import WorkSignal
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.utils.di.di_container import inject

if TYPE_CHECKING:
    from ray.actor import ActorHandle


class CampaignService:
    """
    Top-level campaign functionality integration.
    Exposes an interface for submission, monitoring, and cancellation of campaigns.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        campaign_manager: CampaignManager,
        campaign_optimizer_manager: CampaignOptimizerManager,
        campaign_executor_factory: CampaignExecutorFactory,
        db_interface: AbstractSqlDbInterface,
        work_signal: WorkSignal,
    ):
        self._configuration_manager = configuration_manager
        self._campaign_manager = campaign_manager
        self._campaign_optimizer_manager = campaign_optimizer_manager
        self._campaign_executor_factory = campaign_executor_factory
        self._db_interface = db_interface
        self._work_signal = work_signal

        self._campaign_submission_lock = asyncio.Lock()
        self._submitted_campaigns: dict[str, CampaignExecutor] = {}
        self._campaign_cancellation_queue = asyncio.Queue(maxsize=100)

    async def get_campaign(self, db: AsyncDbSession, campaign_name: str) -> Campaign | None:
        """Get a campaign by its unique identifier."""
        return await self._campaign_manager.get_campaign(db, campaign_name)

    async def submit_campaign(
        self,
        db: AsyncDbSession,
        campaign_submission: CampaignSubmission,
    ) -> None:
        """Submit a new campaign for execution."""
        campaign_name = campaign_submission.name
        protocol_type = campaign_submission.protocol

        self._validate_protocol_type(protocol_type)

        async with self._campaign_submission_lock:
            if campaign_name in self._submitted_campaigns:
                log.warning(f"Campaign '{campaign_name}' is already submitted. Ignoring new submission.")
                return

            campaign_executor = self._campaign_executor_factory.create(campaign_submission)

            try:
                await campaign_executor.start_campaign(db)
                await db.commit()
                self._submitted_campaigns[campaign_name] = campaign_executor
                self._work_signal.signal()
            except EosCampaignExecutionError:
                log.error(f"Failed to submit campaign '{campaign_name}': {traceback.format_exc()}")
                self._submitted_campaigns.pop(campaign_name, None)
                raise

    async def cancel_campaign(self, campaign_name: str) -> None:
        """Cancel a campaign that is currently being executed."""
        if campaign_name in self._submitted_campaigns:
            await self._campaign_cancellation_queue.put(campaign_name)
            log.info(f"Queued campaign '{campaign_name}' for cancellation.")

    async def cancel_campaign_protocol_run(self, protocol_run_name: str) -> bool:
        """
        Queue a specific protocol run that belongs to a campaign for cancellation.
        The actual cancellation will be processed in the campaign's main loop.

        :param protocol_run_name: The name of the protocol run to cancel.
        :return: True if the protocol run was found and queued, False if not found.
        """
        for campaign_executor in self._submitted_campaigns.values():
            if campaign_executor.queue_protocol_run_cancellation(protocol_run_name):
                return True
        return False

    async def fail_running_campaigns(self, db: AsyncDbSession) -> None:
        """Fail all running campaigns."""
        running_campaigns = await self._campaign_manager.get_campaigns(db, status=CampaignStatus.RUNNING.value)
        if not running_campaigns:
            return

        names = [c.name for c in running_campaigns]
        await self._campaign_manager.fail_campaigns_batch(
            db, names, error_message="Campaign was running when the orchestrator restarted"
        )
        log.warning(
            "All running campaigns have been marked as failed. Please review the state of the system and re-submit "
            "with resume=True."
        )

    async def process_campaigns(self) -> None:
        """Try to make progress on all submitted campaigns."""
        if not self._submitted_campaigns:
            return

        # Sort campaigns by priority
        sorted_campaigns = dict(
            sorted(self._submitted_campaigns.items(), key=lambda x: x[1].campaign_submission.priority, reverse=True)
        )

        results = []
        for campaign_name, executor in sorted_campaigns.items():
            result = await self._process_campaign(campaign_name, executor)
            results.append(result)

        completed_campaigns: list[str] = []
        failed_campaigns: list[str] = []

        for campaign_name, completed, failed in results:
            if completed:
                completed_campaigns.append(campaign_name)
            elif failed:
                failed_campaigns.append(campaign_name)

        for campaign_name in completed_campaigns:
            log.info(f"Completed campaign '{campaign_name}'.")
            self._submitted_campaigns[campaign_name].cleanup()
            del self._submitted_campaigns[campaign_name]

        for campaign_name in failed_campaigns:
            log.error(f"Failed campaign '{campaign_name}'.")
            self._submitted_campaigns[campaign_name].cleanup()
            del self._submitted_campaigns[campaign_name]

    async def _process_campaign(
        self, campaign_name: str, campaign_executor: CampaignExecutor
    ) -> tuple[str, bool, bool]:
        try:
            completed = await campaign_executor.progress_campaign()
            return campaign_name, completed, False
        except EosCampaignExecutionError:
            log.error(f"Error in campaign '{campaign_name}': {traceback.format_exc()}")
            return campaign_name, False, True
        except Exception:
            log.error(f"Unexpected error in campaign '{campaign_name}': {traceback.format_exc()}")
            return campaign_name, False, True

    async def process_campaign_cancellations(self) -> None:
        """Try to cancel all campaigns that are queued for cancellation."""
        campaign_names = []
        while not self._campaign_cancellation_queue.empty():
            campaign_names.append(await self._campaign_cancellation_queue.get())

        if not campaign_names:
            return

        cancellation_tasks = [self._submitted_campaigns[cmp_name].cancel_campaign() for cmp_name in campaign_names]
        results = await asyncio.gather(*cancellation_tasks, return_exceptions=True)

        for campaign_name, result in zip(campaign_names, results, strict=True):
            if isinstance(result, Exception):
                log.error(f"Error cancelling campaign '{campaign_name}': {result}")
            self._submitted_campaigns[campaign_name].cleanup()
            del self._submitted_campaigns[campaign_name]

    def _validate_protocol_type(self, protocol_type: str) -> None:
        if protocol_type not in self._configuration_manager.protocols:
            error_msg = f"Cannot submit campaign for protocol type '{protocol_type}' as it does not exist."
            log.error(error_msg)
            raise EosProtocolRunDoesNotExistError(error_msg)

    def _get_running_optimizer(self, campaign_name: str) -> "ActorHandle":
        """Get the optimizer actor for a running campaign, or raise."""
        if campaign_name not in self._submitted_campaigns:
            raise EosCampaignExecutionError(f"Campaign '{campaign_name}' is not currently running.")
        optimizer = self._submitted_campaigns[campaign_name].optimizer
        if optimizer is None:
            raise EosCampaignExecutionError(f"Campaign '{campaign_name}' has no active optimizer.")
        return optimizer

    async def _persist_optimizer_meta(self, campaign_name: str, optimizer: "ActorHandle") -> None:
        meta = await optimizer.get_optimizer_meta.remote()
        if not meta:
            return
        async with self._db_interface.get_async_session() as db:
            current_meta = await self._campaign_manager.get_campaign_meta(db, campaign_name) or {}
            current_beacon = current_meta.get("beacon", {}) or {}
            merged_beacon = {**current_beacon, **meta}
            await self._campaign_manager.update_campaign_meta(db, campaign_name, "beacon", merged_beacon)

    async def add_optimizer_insight(self, campaign_name: str, insight: str) -> None:
        """Add an expert insight to the optimizer of a running campaign."""
        optimizer = self._get_running_optimizer(campaign_name)
        await optimizer.add_insight.remote(insight)
        await self._persist_optimizer_meta(campaign_name, optimizer)

    async def get_optimizer_info(self, campaign_name: str) -> dict[str, Any]:
        """Get optimizer type, runtime params, insights, and journal for a running campaign."""
        if campaign_name not in self._submitted_campaigns:
            raise EosCampaignExecutionError(f"Campaign '{campaign_name}' is not currently running.")

        optimizer = self._submitted_campaigns[campaign_name].optimizer
        if optimizer is None:
            return {"status": "initializing"}

        optimizer_type, runtime_params, meta = await asyncio.gather(
            optimizer.get_optimizer_type.remote(),
            optimizer.get_runtime_params.remote(),
            optimizer.get_optimizer_meta.remote(),
        )

        return {
            "status": "ready",
            "optimizer_type": optimizer_type,
            "runtime_params": runtime_params,
            "insights": meta.get("insights", []) if meta else [],
            "journal": meta.get("journal", []) if meta else [],
        }

    async def update_optimizer_params(self, campaign_name: str, params: dict[str, Any]) -> None:
        """Update runtime-safe optimizer parameters for a running campaign."""
        optimizer = self._get_running_optimizer(campaign_name)
        await optimizer.set_runtime_params.remote(params)
        await self._persist_optimizer_meta(campaign_name, optimizer)

    def get_optimizer_defaults(self, protocol_type: str) -> tuple[str, dict[str, Any]] | None:
        """Get optimizer type name and default params for a protocol type."""
        return self._campaign_optimizer_manager.get_optimizer_defaults(protocol_type)

    @property
    def submitted_campaigns(self) -> dict[str, CampaignExecutor]:
        return self._submitted_campaigns
