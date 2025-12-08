from datetime import datetime, UTC
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

    async def set_experiments_completed(self, db: AsyncDbSession, campaign_name: str, count: int) -> None:
        """Set the experiments_completed count for a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        await db.execute(
            update(CampaignModel).where(CampaignModel.name == campaign_name).values(experiments_completed=count)
        )

    async def update_campaign_definition(self, db: AsyncDbSession, definition: CampaignDefinition) -> None:
        """Update the campaign definition fields in the database."""
        await self._validate_campaign_exists(db, definition.name)

        await db.execute(
            update(CampaignModel)
            .where(CampaignModel.name == definition.name)
            .values(
                priority=definition.priority,
                max_experiments=definition.max_experiments,
                max_concurrent_experiments=definition.max_concurrent_experiments,
                optimize=definition.optimize,
                optimizer_ip=definition.optimizer_ip,
                global_parameters=definition.global_parameters,
                experiment_parameters=definition.experiment_parameters,
                meta=definition.meta,
            )
        )

    async def delete_non_completed_campaign_experiments(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Delete all non-completed experiments from a campaign (for resume)."""
        await self._validate_campaign_exists(db, campaign_name)

        # Get non-completed experiments for this campaign
        stmt = select(ExperimentModel.name).where(
            ExperimentModel.campaign == campaign_name,
            ExperimentModel.status.not_in([ExperimentStatus.COMPLETED]),
        )
        result = await db.execute(stmt)
        experiment_names = [row[0] for row in result.all()]

        # Delete tasks and experiments
        for experiment_name in experiment_names:
            await db.execute(delete(TaskModel).where(TaskModel.experiment_name == experiment_name))
            await db.execute(delete(ExperimentModel).where(ExperimentModel.name == experiment_name))

    async def get_campaign_experiment_names(
        self, db: AsyncDbSession, campaign_name: str, status: ExperimentStatus | None = None
    ) -> list[str]:
        """Get all experiment names of a campaign with an optional status filter."""
        stmt = select(ExperimentModel.name).where(ExperimentModel.campaign == campaign_name)
        if status:
            stmt = stmt.where(ExperimentModel.status == status)

        result = await db.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_running_campaign_experiment_count(self, db: AsyncDbSession, campaign_name: str) -> int:
        """Get count of running experiments for a campaign."""
        from sqlalchemy import func

        stmt = select(func.count()).where(
            ExperimentModel.campaign == campaign_name,
            ExperimentModel.status == ExperimentStatus.RUNNING,
        )
        result = await db.execute(stmt)
        return result.scalar_one()

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
            update_fields["start_time"] = datetime.now(UTC)
        elif new_status in [
            CampaignStatus.COMPLETED,
            CampaignStatus.CANCELLED,
            CampaignStatus.FAILED,
        ]:
            update_fields["end_time"] = datetime.now(UTC)

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
