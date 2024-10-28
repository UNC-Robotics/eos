import asyncio
from datetime import datetime, timezone
from typing import Any

from eos.campaigns.entities.campaign import Campaign, CampaignStatus, CampaignDefinition
from eos.campaigns.exceptions import EosCampaignStateError
from eos.campaigns.repositories.campaign_repository import CampaignRepository
from eos.configuration.configuration_manager import ConfigurationManager
from eos.experiments.entities.experiment import ExperimentStatus
from eos.experiments.repositories.experiment_repository import ExperimentRepository
from eos.logging.logger import log
from eos.persistence.async_mongodb_interface import AsyncMongoDbInterface
from eos.tasks.repositories.task_repository import TaskRepository


class CampaignManager:
    """
    Responsible for managing the state of all experiment campaigns in EOS and tracking their execution.
    """

    def __init__(self, configuration_manager: ConfigurationManager, db_interface: AsyncMongoDbInterface):
        self._configuration_manager = configuration_manager
        self._session_factory = db_interface.session_factory
        self._campaigns = None
        self._experiments = None
        self._tasks = None

    async def initialize(self, db_interface: AsyncMongoDbInterface) -> None:
        self._campaigns = CampaignRepository(db_interface)
        await self._campaigns.initialize()

        self._experiments = ExperimentRepository(db_interface)
        await self._experiments.initialize()

        self._tasks = TaskRepository(db_interface)
        await self._tasks.initialize()

        log.debug("Campaign manager initialized.")

    async def create_campaign(
        self,
        definition: CampaignDefinition,
    ) -> None:
        """Create a new campaign."""
        campaign_id = definition.id
        experiment_type = definition.experiment_type

        if await self._campaigns.get_one(id=campaign_id):
            raise EosCampaignStateError(f"Campaign '{campaign_id}' already exists.")

        experiment_config = self._configuration_manager.experiments.get(experiment_type)
        if not experiment_config:
            raise EosCampaignStateError(f"Experiment type '{experiment_type}' not found in the configuration.")

        campaign = Campaign.from_definition(definition)
        await self._campaigns.create(campaign.model_dump())

        log.info(f"Created campaign '{campaign_id}'.")

    async def delete_campaign(self, campaign_id: str) -> None:
        """
        Delete a campaign.
        """
        if not self._campaigns.exists(id=campaign_id):
            raise EosCampaignStateError(f"Campaign '{campaign_id}' does not exist.")

        await self._campaigns.delete_one(id=campaign_id)

        log.info(f"Deleted campaign '{campaign_id}'.")

    async def start_campaign(self, campaign_id: str) -> None:
        """
        Start a campaign.
        """
        await self._set_campaign_status(campaign_id, CampaignStatus.RUNNING)

    async def complete_campaign(self, campaign_id: str) -> None:
        """
        Complete a campaign.
        """
        await self._set_campaign_status(campaign_id, CampaignStatus.COMPLETED)

    async def cancel_campaign(self, campaign_id: str) -> None:
        """
        Cancel a campaign.
        """
        await self._set_campaign_status(campaign_id, CampaignStatus.CANCELLED)

    async def suspend_campaign(self, campaign_id: str) -> None:
        """
        Suspend a campaign.
        """
        await self._set_campaign_status(campaign_id, CampaignStatus.SUSPENDED)

    async def fail_campaign(self, campaign_id: str) -> None:
        """
        Fail a campaign.
        """
        await self._set_campaign_status(campaign_id, CampaignStatus.FAILED)

    async def get_campaign(self, campaign_id: str) -> Campaign | None:
        """
        Get a campaign.
        """
        campaign = await self._campaigns.get_one(id=campaign_id)
        return Campaign(**campaign) if campaign else None

    async def get_campaigns(self, **query: dict[str, Any]) -> list[Campaign]:
        """
        Query campaigns with arbitrary parameters.

        :param query: Dictionary of query parameters.
        """
        campaigns = await self._campaigns.get_all(**query)
        return [Campaign(**campaign) for campaign in campaigns]

    async def _set_campaign_status(self, campaign_id: str, new_status: CampaignStatus) -> None:
        """
        Set the status of a campaign.
        """
        update_fields = {"status": new_status.value}
        if new_status == CampaignStatus.RUNNING:
            update_fields["start_time"] = datetime.now(tz=timezone.utc)
        elif new_status in [
            CampaignStatus.COMPLETED,
            CampaignStatus.CANCELLED,
            CampaignStatus.FAILED,
        ]:
            update_fields["end_time"] = datetime.now(tz=timezone.utc)

        await self._campaigns.update_one(update_fields, id=campaign_id)

    async def increment_iteration(self, campaign_id: str) -> None:
        """
        Increment the iteration count of a campaign.
        """
        await self._campaigns.increment_campaign_iteration(campaign_id)

    async def add_campaign_experiment(self, campaign_id: str, experiment_id: str) -> None:
        """
        Add an experiment to a campaign.
        """
        await self._campaigns.add_current_experiment(campaign_id, experiment_id)

    async def delete_campaign_experiment(self, campaign_id: str, experiment_id: str) -> None:
        """
        Remove an experiment from a campaign.
        """
        await self._campaigns.remove_current_experiment(campaign_id, experiment_id)

    async def delete_current_campaign_experiments(self, campaign_id: str) -> None:
        """
        Delete all current experiments from a campaign.
        """
        campaign = await self.get_campaign(campaign_id)

        for experiment_id in campaign.current_experiment_ids:
            await asyncio.gather(
                self._experiments.delete_one(id=experiment_id),
                self._tasks.delete_many(experiment_id=experiment_id),
            )

        await self._campaigns.clear_current_experiments(campaign_id)

    async def get_campaign_experiment_ids(self, campaign_id: str, status: ExperimentStatus | None = None) -> list[str]:
        """
        Get all experiment IDs of a campaign with an optional status filter.

        :param campaign_id: The ID of the campaign.
        :param status: Optional status to filter experiments.
        :return: A list of experiment IDs.
        """
        return await self._experiments.get_experiment_ids_by_campaign(campaign_id, status)

    async def set_pareto_solutions(self, campaign_id: str, pareto_solutions: dict[str, Any]) -> None:
        """
        Set the Pareto solutions for a campaign.
        """
        await self._campaigns.update_one({"pareto_solutions": pareto_solutions}, id=campaign_id)
