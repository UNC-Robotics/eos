import asyncio
import traceback

from eos.campaigns.campaign_executor import CampaignExecutor
from eos.campaigns.campaign_executor_factory import CampaignExecutorFactory
from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.entities.campaign import Campaign, CampaignStatus, CampaignDefinition
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.orchestration.exceptions import EosExperimentDoesNotExistError
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.utils.di.di_container import inject_all


class CampaignModule:
    """
    Top-level campaign functionality integration.
    Exposes an interface for submission, monitoring, and cancellation of campaigns.
    """

    @inject_all
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        campaign_manager: CampaignManager,
        campaign_executor_factory: CampaignExecutorFactory,
        db_interface: AbstractSqlDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._campaign_manager = campaign_manager
        self._campaign_executor_factory = campaign_executor_factory
        self._db_interface = db_interface

        self._campaign_submission_lock = asyncio.Lock()
        self._submitted_campaigns: dict[str, CampaignExecutor] = {}
        self._campaign_cancellation_queue = asyncio.Queue(maxsize=100)

    async def get_campaign(self, db: AsyncDbSession, campaign_id: str) -> Campaign | None:
        """Get a campaign by its unique identifier."""
        return await self._campaign_manager.get_campaign(db, campaign_id)

    async def submit_campaign(
        self,
        db: AsyncDbSession,
        campaign_definition: CampaignDefinition,
    ) -> None:
        """Submit a new campaign for execution."""
        campaign_id = campaign_definition.id
        experiment_type = campaign_definition.experiment_type

        self._validate_experiment_type(experiment_type)

        async with self._campaign_submission_lock:
            if campaign_id in self._submitted_campaigns:
                log.warning(f"Campaign '{campaign_id}' is already submitted. Ignoring new submission.")
                return

            campaign_executor = self._campaign_executor_factory.create(campaign_definition)

            try:
                await campaign_executor.start_campaign(db)
                self._submitted_campaigns[campaign_id] = campaign_executor
            except EosCampaignExecutionError:
                log.error(f"Failed to submit campaign '{campaign_id}': {traceback.format_exc()}")
                del self._submitted_campaigns[campaign_id]
                return

            log.info(f"Submitted campaign '{campaign_id}'.")

    async def cancel_campaign(self, campaign_id: str) -> None:
        """Cancel a campaign that is currently being executed."""
        if campaign_id in self._submitted_campaigns:
            await self._campaign_cancellation_queue.put(campaign_id)
            log.info(f"Queued campaign '{campaign_id}' for cancellation.")

    async def fail_running_campaigns(self, db: AsyncDbSession) -> None:
        """Fail all running campaigns."""
        running_campaigns = await self._campaign_manager.get_campaigns(db, status=CampaignStatus.RUNNING.value)

        for campaign in running_campaigns:
            await self._campaign_manager.fail_campaign(db, campaign.id)

        if running_campaigns:
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
            sorted(self._submitted_campaigns.items(), key=lambda x: x[1].campaign_definition.priority, reverse=True)
        )

        results = []
        for campaign_id, executor in sorted_campaigns.items():
            result = await self._process_campaign(campaign_id, executor)
            results.append(result)

        completed_campaigns: list[str] = []
        failed_campaigns: list[str] = []

        for campaign_id, completed, failed in results:
            if completed:
                completed_campaigns.append(campaign_id)
            elif failed:
                failed_campaigns.append(campaign_id)

        for campaign_id in completed_campaigns:
            log.info(f"Completed campaign '{campaign_id}'.")
            self._submitted_campaigns[campaign_id].cleanup()
            del self._submitted_campaigns[campaign_id]

        for campaign_id in failed_campaigns:
            log.error(f"Failed campaign '{campaign_id}'.")
            self._submitted_campaigns[campaign_id].cleanup()
            del self._submitted_campaigns[campaign_id]

    async def _process_campaign(self, campaign_id: str, campaign_executor: CampaignExecutor) -> tuple[str, bool, bool]:
        try:
            completed = await campaign_executor.progress_campaign()
            return campaign_id, completed, False
        except EosCampaignExecutionError:
            log.error(f"Error in campaign '{campaign_id}': {traceback.format_exc()}")
            return campaign_id, False, True

    async def process_campaign_cancellations(self) -> None:
        """Try to cancel all campaigns that are queued for cancellation."""
        campaign_ids = []
        while not self._campaign_cancellation_queue.empty():
            campaign_ids.append(await self._campaign_cancellation_queue.get())

        if not campaign_ids:
            return

        cancellation_tasks = [self._submitted_campaigns[cmp_id].cancel_campaign() for cmp_id in campaign_ids]
        await asyncio.gather(*cancellation_tasks)

        for campaign_id in campaign_ids:
            self._submitted_campaigns[campaign_id].cleanup()
            del self._submitted_campaigns[campaign_id]

    def _validate_experiment_type(self, experiment_type: str) -> None:
        if experiment_type not in self._configuration_manager.experiments:
            log.error(f"Cannot submit experiment of type '{experiment_type}' as it does not exist.")
            raise EosExperimentDoesNotExistError

    @property
    def submitted_campaigns(self) -> dict[str, CampaignExecutor]:
        return self._submitted_campaigns
