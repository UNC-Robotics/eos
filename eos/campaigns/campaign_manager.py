from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, exists, delete, update

from eos.campaigns.entities.campaign import (
    Campaign,
    CampaignStatus,
    CampaignDefinition,
    CampaignModel,
    CampaignSampleModel,
)
from eos.campaigns.exceptions import EosCampaignStateError
from eos.configuration.configuration_manager import ConfigurationManager
from eos.experiments.entities.experiment import ExperimentStatus, ExperimentModel
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import TaskModel
from eos.utils.di.di_container import inject


class CampaignManager:
    """
    Responsible for managing the state of all experiment campaigns in EOS and tracking their execution.
    """

    @inject
    def __init__(self, configuration_manager: ConfigurationManager):
        self._configuration_manager = configuration_manager

        log.debug("Campaign manager initialized.")

    async def _check_campaign_exists(self, db: AsyncDbSession, campaign_name: str) -> bool:
        """Check if a campaign exists."""
        result = await db.execute(select(exists().where(CampaignModel.name == campaign_name)))
        return bool(result.scalar_one_or_none())

    async def _validate_campaign_exists(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Validate campaign existence or raise an error."""
        if not await self._check_campaign_exists(db, campaign_name):
            raise EosCampaignStateError(f"Campaign '{campaign_name}' does not exist.")

    async def create_campaign(self, db: AsyncDbSession, definition: CampaignDefinition) -> None:
        """Create a new campaign."""
        if await self._check_campaign_exists(db, definition.name):
            raise EosCampaignStateError(f"Campaign '{definition.name}' already exists.")

        experiment_config = self._configuration_manager.experiments.get(definition.experiment_type)
        if not experiment_config:
            raise EosCampaignStateError(
                f"Experiment type '{definition.experiment_type}' not found in the configuration."
            )

        campaign = Campaign.from_definition(definition)
        campaign_model = CampaignModel(**campaign.model_dump())

        db.add(campaign_model)
        await db.flush()

        log.info(f"Created campaign '{definition.name}'.")

    async def delete_campaign(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Delete a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        await db.execute(delete(CampaignSampleModel).where(CampaignSampleModel.campaign_name == campaign_name))
        await db.execute(delete(CampaignModel).where(CampaignModel.name == campaign_name))

        log.info(f"Deleted campaign '{campaign_name}'.")

    async def get_campaign(self, db: AsyncDbSession, campaign_name: str) -> Campaign | None:
        """Get a campaign by name."""
        result = await db.execute(select(CampaignModel).where(CampaignModel.name == campaign_name))
        if campaign_model := result.scalar_one_or_none():
            return Campaign.model_validate(campaign_model)
        return None

    async def get_campaigns(self, db: AsyncDbSession, **filters: Any) -> list[Campaign]:
        """Query campaigns with arbitrary parameters."""
        stmt = select(CampaignModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(CampaignModel, key) == value)

        result = await db.execute(stmt)
        return [Campaign.model_validate(model) for model in result.scalars()]

    async def increment_iteration(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Increment the iteration count of a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        await db.execute(
            update(CampaignModel)
            .where(CampaignModel.name == campaign_name)
            .values(experiments_completed=CampaignModel.experiments_completed + 1)
        )

    async def add_campaign_experiment(self, db: AsyncDbSession, campaign_name: str, experiment_name: str) -> None:
        """Add an experiment to a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        result = await db.execute(
            select(CampaignModel.current_experiment_names).where(CampaignModel.name == campaign_name)
        )
        current_experiments = result.scalar_one_or_none() or []

        updated_experiments = [*current_experiments, experiment_name]
        await db.execute(
            update(CampaignModel)
            .where(CampaignModel.name == campaign_name)
            .values(current_experiment_names=updated_experiments)
        )

    async def delete_campaign_experiment(self, db: AsyncDbSession, campaign_name: str, experiment_name: str) -> None:
        """Remove an experiment from a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        result = await db.execute(
            select(CampaignModel.current_experiment_names).where(CampaignModel.name == campaign_name)
        )
        if current_experiments := result.scalar_one_or_none():
            updated_experiments = [exp for exp in current_experiments if exp != experiment_name]
            await db.execute(
                update(CampaignModel)
                .where(CampaignModel.name == campaign_name)
                .values(current_experiment_names=updated_experiments)
            )

    async def delete_current_campaign_experiments(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Delete all current experiments from a campaign."""
        campaign = await self.get_campaign(db, campaign_name)
        if not campaign:
            raise EosCampaignStateError(f"Campaign '{campaign_name}' does not exist.")

        for experiment_name in campaign.current_experiment_names:
            await db.execute(delete(TaskModel).where(TaskModel.experiment_name == experiment_name))
            await db.execute(delete(ExperimentModel).where(ExperimentModel.name == experiment_name))

        await db.execute(
            update(CampaignModel).where(CampaignModel.name == campaign_name).values(current_experiment_names=[])
        )

    async def get_campaign_experiment_names(
        self, db: AsyncDbSession, campaign_name: str, status: ExperimentStatus | None = None
    ) -> list[str]:
        """Get all experiment names of a campaign with an optional status filter."""
        stmt = select(ExperimentModel.name).where(ExperimentModel.name.like(f"{campaign_name}%"))
        if status:
            stmt = stmt.where(ExperimentModel.status == status)

        result = await db.execute(stmt)
        return [row[0] for row in result.all()]

    async def set_pareto_solutions(
        self, db: AsyncDbSession, campaign_name: str, pareto_solutions: list[dict[str, Any]]
    ) -> None:
        """Set the Pareto solutions for a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        await db.execute(
            update(CampaignModel).where(CampaignModel.name == campaign_name).values(pareto_solutions=pareto_solutions)
        )

    async def _set_campaign_status(self, db: AsyncDbSession, campaign_name: str, new_status: CampaignStatus) -> None:
        """Set the status of a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        update_fields = {"status": new_status}
        if new_status == CampaignStatus.RUNNING:
            update_fields["start_time"] = datetime.now(timezone.utc)
        elif new_status in [
            CampaignStatus.COMPLETED,
            CampaignStatus.CANCELLED,
            CampaignStatus.FAILED,
        ]:
            update_fields["end_time"] = datetime.now(timezone.utc)

        await db.execute(update(CampaignModel).where(CampaignModel.name == campaign_name).values(**update_fields))

    async def start_campaign(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Start a campaign."""
        await self._set_campaign_status(db, campaign_name, CampaignStatus.RUNNING)

    async def complete_campaign(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Complete a campaign."""
        await self._set_campaign_status(db, campaign_name, CampaignStatus.COMPLETED)

    async def cancel_campaign(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Cancel a campaign."""
        await self._set_campaign_status(db, campaign_name, CampaignStatus.CANCELLED)

    async def suspend_campaign(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Suspend a campaign."""
        await self._set_campaign_status(db, campaign_name, CampaignStatus.SUSPENDED)

    async def fail_campaign(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Fail a campaign."""
        await self._set_campaign_status(db, campaign_name, CampaignStatus.FAILED)
