from datetime import datetime, UTC
from typing import Any

from sqlalchemy import func, select, exists, delete, update

from eos.campaigns.entities.campaign import (
    Campaign,
    CampaignStatus,
    CampaignSubmission,
    CampaignModel,
    CampaignSampleModel,
)
from eos.campaigns.exceptions import EosCampaignStateError
from eos.configuration.configuration_manager import ConfigurationManager
from eos.protocols.entities.protocol_run import ProtocolRunStatus, ProtocolRunModel
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import TaskModel
from eos.utils.di.di_container import inject


class CampaignManager:
    """
    Responsible for managing the state of all campaigns in EOS and tracking their execution.
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

    async def create_campaign(self, db: AsyncDbSession, submission: CampaignSubmission) -> None:
        """Create a new campaign."""
        if await self._check_campaign_exists(db, submission.name):
            raise EosCampaignStateError(f"Campaign '{submission.name}' already exists.")

        protocol_def = self._configuration_manager.protocols.get(submission.protocol)
        if not protocol_def:
            raise EosCampaignStateError(f"ProtocolRun type '{submission.protocol}' not found in the configuration.")

        campaign = Campaign.from_submission(submission)
        campaign_model = CampaignModel(**campaign.model_dump())

        db.add(campaign_model)
        await db.flush()

        log.info(f"Created campaign '{submission.name}'.")

    async def delete_campaign(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Delete a campaign and all associated protocols and samples."""
        await self._validate_campaign_exists(db, campaign_name)

        # Get all protocol run names for this campaign
        stmt = select(ProtocolRunModel.name).where(ProtocolRunModel.campaign == campaign_name)
        result = await db.execute(stmt)
        protocol_run_names = [row[0] for row in result.all()]

        # Delete protocols and their tasks
        if protocol_run_names:
            await db.execute(delete(TaskModel).where(TaskModel.protocol_run_name.in_(protocol_run_names)))
            await db.execute(delete(ProtocolRunModel).where(ProtocolRunModel.campaign == campaign_name))

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
            .values(protocol_runs_completed=CampaignModel.protocol_runs_completed + 1)
        )

    async def set_protocol_runs_completed(self, db: AsyncDbSession, campaign_name: str, count: int) -> None:
        """Set the protocol_runs_completed count for a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        await db.execute(
            update(CampaignModel).where(CampaignModel.name == campaign_name).values(protocol_runs_completed=count)
        )

    async def update_campaign_submission(self, db: AsyncDbSession, submission: CampaignSubmission) -> None:
        """Update the campaign submission fields in the database."""
        await self._validate_campaign_exists(db, submission.name)

        await db.execute(
            update(CampaignModel)
            .where(CampaignModel.name == submission.name)
            .values(
                priority=submission.priority,
                max_protocol_runs=submission.max_protocol_runs,
                max_concurrent_protocol_runs=submission.max_concurrent_protocol_runs,
                optimize=submission.optimize,
                optimizer_ip=submission.optimizer_ip,
                global_parameters=submission.global_parameters,
                protocol_run_parameters=submission.protocol_run_parameters,
                meta=submission.meta,
            )
        )

    async def delete_non_completed_campaign_protocol_runs(self, db: AsyncDbSession, campaign_name: str) -> None:
        """Delete all non-completed protocols from a campaign (for resume)."""
        await self._validate_campaign_exists(db, campaign_name)

        # Get non-completed protocols for this campaign
        stmt = select(ProtocolRunModel.name).where(
            ProtocolRunModel.campaign == campaign_name,
            ProtocolRunModel.status.not_in([ProtocolRunStatus.COMPLETED]),
        )
        result = await db.execute(stmt)
        protocol_run_names = [row[0] for row in result.all()]

        if protocol_run_names:
            await db.execute(delete(TaskModel).where(TaskModel.protocol_run_name.in_(protocol_run_names)))
            await db.execute(delete(ProtocolRunModel).where(ProtocolRunModel.name.in_(protocol_run_names)))

    async def get_campaign_protocol_run_names(
        self, db: AsyncDbSession, campaign_name: str, status: ProtocolRunStatus | None = None
    ) -> list[str]:
        """Get all protocol run names of a campaign with an optional status filter."""
        stmt = select(ProtocolRunModel.name).where(ProtocolRunModel.campaign == campaign_name)
        if status:
            stmt = stmt.where(ProtocolRunModel.status == status)

        result = await db.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_running_campaign_protocol_run_count(self, db: AsyncDbSession, campaign_name: str) -> int:
        """Get count of running protocol runs for a campaign."""
        stmt = select(func.count()).where(
            ProtocolRunModel.campaign == campaign_name,
            ProtocolRunModel.status == ProtocolRunStatus.RUNNING,
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    async def get_campaign_meta(self, db: AsyncDbSession, campaign_name: str) -> dict[str, Any] | None:
        """Get the meta dict for a campaign."""
        result = await db.execute(select(CampaignModel.meta).where(CampaignModel.name == campaign_name))
        return result.scalar_one_or_none()

    async def update_campaign_meta(self, db: AsyncDbSession, campaign_name: str, key: str, value: Any) -> None:
        """Merge a key into campaign meta."""
        result = await db.execute(select(CampaignModel.meta).where(CampaignModel.name == campaign_name))
        current_meta = result.scalar_one_or_none()
        if current_meta is not None:
            await db.execute(
                update(CampaignModel)
                .where(CampaignModel.name == campaign_name)
                .values(meta={**current_meta, key: value})
            )

    async def set_pareto_solutions(
        self, db: AsyncDbSession, campaign_name: str, pareto_solutions: list[dict[str, Any]]
    ) -> None:
        """Set the Pareto solutions for a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        await db.execute(
            update(CampaignModel).where(CampaignModel.name == campaign_name).values(pareto_solutions=pareto_solutions)
        )

    async def _set_campaign_status(
        self, db: AsyncDbSession, campaign_name: str, new_status: CampaignStatus, error_message: str | None = None
    ) -> None:
        """Set the status of a campaign."""
        await self._validate_campaign_exists(db, campaign_name)

        update_fields: dict = {"status": new_status}
        if new_status == CampaignStatus.RUNNING:
            update_fields["start_time"] = datetime.now(UTC)
            update_fields["error_message"] = None
        elif new_status in [
            CampaignStatus.COMPLETED,
            CampaignStatus.CANCELLED,
            CampaignStatus.FAILED,
        ]:
            update_fields["end_time"] = datetime.now(UTC)

        if error_message is not None:
            update_fields["error_message"] = error_message

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

    async def fail_campaign(self, db: AsyncDbSession, campaign_name: str, error_message: str | None = None) -> None:
        """Fail a campaign."""
        await self._set_campaign_status(db, campaign_name, CampaignStatus.FAILED, error_message=error_message)

    async def fail_campaigns_batch(
        self, db: AsyncDbSession, names: list[str], error_message: str | None = None
    ) -> None:
        if not names:
            return
        update_fields: dict = {
            "status": CampaignStatus.FAILED,
            "end_time": datetime.now(UTC),
        }
        if error_message is not None:
            update_fields["error_message"] = error_message
        await db.execute(update(CampaignModel).where(CampaignModel.name.in_(names)).values(**update_fields))
