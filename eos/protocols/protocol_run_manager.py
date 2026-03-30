from datetime import datetime, UTC
from typing import Any

from sqlalchemy import exists, select, delete, and_, update

from eos.allocation.entities.device_allocation import DeviceAllocationModel
from eos.allocation.entities.resource_allocation import ResourceAllocationModel
from eos.campaigns.entities.campaign import CampaignSampleModel
from eos.configuration.configuration_manager import ConfigurationManager
from eos.protocols.entities.protocol_run import ProtocolRun, ProtocolRunStatus, ProtocolRunSubmission, ProtocolRunModel
from eos.protocols.exceptions import EosProtocolRunStateError
from eos.logging.logger import log

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import TaskModel, TaskStatus
from eos.utils.di.di_container import inject


class ProtocolRunManager:
    """
    Responsible for managing the state of all protocol runs in EOS and tracking their execution.
    """

    @inject
    def __init__(self, configuration_manager: ConfigurationManager):
        self._configuration_manager = configuration_manager
        log.debug("Protocol run manager initialized.")

    async def _check_protocol_run_exists(self, db: AsyncDbSession, protocol_run_name: str) -> bool:
        """Check if a protocol run exists."""
        result = await db.execute(select(exists().where(ProtocolRunModel.name == protocol_run_name)))
        return bool(result.scalar())

    async def _validate_protocol_run_exists(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        """Validate protocol run existence or raise an error."""
        if not await self._check_protocol_run_exists(db, protocol_run_name):
            raise EosProtocolRunStateError(f"Protocol run '{protocol_run_name}' does not exist.")

    async def create_protocol_run(
        self, db: AsyncDbSession, submission: ProtocolRunSubmission, campaign: str | None = None
    ) -> None:
        """Create a new protocol run from a submission."""
        if await self._check_protocol_run_exists(db, submission.name):
            raise EosProtocolRunStateError(
                f"Protocol run '{submission.name}' already exists. Please create a protocol run with a different name."
            )

        protocol_def = self._configuration_manager.protocols.get(submission.type)
        if not protocol_def:
            raise EosProtocolRunStateError(f"Protocol type '{submission.type}' not found in the configuration.")

        protocol_run = ProtocolRun.from_submission(submission)
        protocol_run.campaign = campaign
        protocol_run_model = ProtocolRunModel(**protocol_run.model_dump())

        db.add(protocol_run_model)
        await db.flush()

        log.info(f"Created protocol run '{submission.name}'.")

    async def update_protocol_run_parameters(
        self, db: AsyncDbSession, protocol_run_name: str, parameters: dict[str, dict[str, Any]]
    ) -> None:
        """Update the parameters of an existing protocol run."""
        await self._validate_protocol_run_exists(db, protocol_run_name)
        await db.execute(
            update(ProtocolRunModel).where(ProtocolRunModel.name == protocol_run_name).values(parameters=parameters)
        )

    async def delete_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        """Delete a protocol run and all associated records."""
        await self._validate_protocol_run_exists(db, protocol_run_name)

        # Delete all records that reference this protocol run
        await db.execute(delete(TaskModel).where(TaskModel.protocol_run_name == protocol_run_name))
        await db.execute(
            delete(DeviceAllocationModel).where(DeviceAllocationModel.protocol_run_name == protocol_run_name)
        )
        await db.execute(
            delete(ResourceAllocationModel).where(ResourceAllocationModel.protocol_run_name == protocol_run_name)
        )
        await db.execute(delete(CampaignSampleModel).where(CampaignSampleModel.protocol_run_name == protocol_run_name))
        await db.execute(delete(ProtocolRunModel).where(ProtocolRunModel.name == protocol_run_name))

        log.info(f"Deleted protocol run '{protocol_run_name}'.")

    async def get_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> ProtocolRun | None:
        """Get a protocol run by name."""
        result = await db.execute(select(ProtocolRunModel).where(ProtocolRunModel.name == protocol_run_name))
        if protocol_run_model := result.scalar_one_or_none():
            return ProtocolRun.model_validate(protocol_run_model)
        return None

    async def get_protocol_runs(self, db: AsyncDbSession, **filters: Any) -> list[ProtocolRun]:
        """Query protocol runs with arbitrary parameters."""
        stmt = select(ProtocolRunModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(ProtocolRunModel, key) == value)

        result = await db.execute(stmt)
        return [ProtocolRun.model_validate(model) for model in result.scalars()]

    async def get_running_tasks(self, db: AsyncDbSession, protocol_run_name: str | None) -> set[str]:
        """Get the set of currently running task names for a protocol run."""
        result = await db.execute(
            select(TaskModel.name).where(
                and_(TaskModel.protocol_run_name == protocol_run_name, TaskModel.status == TaskStatus.RUNNING)
            )
        )
        return {task_name for (task_name,) in result.all()}

    async def get_completed_tasks(self, db: AsyncDbSession, protocol_run_name: str) -> set[str]:
        """Get the set of completed task names for a protocol run."""
        result = await db.execute(
            select(TaskModel.name).where(
                and_(TaskModel.protocol_run_name == protocol_run_name, TaskModel.status == TaskStatus.COMPLETED)
            )
        )
        return {task_name for (task_name,) in result.all()}

    async def get_all_completed_tasks(self, db: AsyncDbSession, protocol_run_names: list[str]) -> dict[str, set[str]]:
        """
        Get completed tasks for all protocol runs in the provided list.
        Returns a dictionary mapping protocol_run_name to a set of completed task names.
        """
        result = await db.execute(
            select(TaskModel.protocol_run_name, TaskModel.name).where(
                and_(TaskModel.protocol_run_name.in_(protocol_run_names), TaskModel.status == TaskStatus.COMPLETED)
            )
        )

        completed_mapping = {}
        for run_name, task_name in result.all():
            if run_name not in completed_mapping:
                completed_mapping[run_name] = set()
            completed_mapping[run_name].add(task_name)

        # Ensure all protocol_run_names are present in the result
        for run_name in protocol_run_names:
            completed_mapping.setdefault(run_name, set())
        return completed_mapping

    async def get_all_running_tasks(self, db: AsyncDbSession, protocol_run_names: list[str]) -> dict[str, set[str]]:
        """
        Get running tasks for all protocol runs in the provided list.
        Returns a dictionary mapping protocol_run_name to a set of running task names.
        """
        result = await db.execute(
            select(TaskModel.protocol_run_name, TaskModel.name).where(
                and_(TaskModel.protocol_run_name.in_(protocol_run_names), TaskModel.status == TaskStatus.RUNNING)
            )
        )

        running_mapping = {}
        for run_name, task_name in result.all():
            if run_name not in running_mapping:
                running_mapping[run_name] = set()
            running_mapping[run_name].add(task_name)

        # Ensure all protocol_run_names are present in the result
        for run_name in protocol_run_names:
            running_mapping.setdefault(run_name, set())
        return running_mapping

    async def delete_non_completed_tasks(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        """Delete running, failed and cancelled tasks for a protocol run."""
        await self._validate_protocol_run_exists(db, protocol_run_name)

        # Delete non-completed tasks (running, failed, cancelled)
        await db.execute(
            delete(TaskModel).where(
                and_(
                    TaskModel.protocol_run_name == protocol_run_name,
                    TaskModel.status.in_([TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED]),
                )
            )
        )

    async def _set_protocol_run_status(
        self,
        db: AsyncDbSession,
        protocol_run_name: str,
        new_status: ProtocolRunStatus,
        error_message: str | None = None,
    ) -> None:
        """Set the status of a protocol run."""
        await self._validate_protocol_run_exists(db, protocol_run_name)

        update_fields: dict = {"status": new_status}
        if new_status == ProtocolRunStatus.RUNNING:
            update_fields["start_time"] = datetime.now(UTC)
            update_fields["error_message"] = None
        elif new_status in [
            ProtocolRunStatus.COMPLETED,
            ProtocolRunStatus.CANCELLED,
            ProtocolRunStatus.FAILED,
        ]:
            update_fields["end_time"] = datetime.now(UTC)

        if error_message is not None:
            update_fields["error_message"] = error_message

        await db.execute(
            update(ProtocolRunModel).where(ProtocolRunModel.name == protocol_run_name).values(**update_fields)
        )

    async def start_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        """Start a protocol run."""
        await self._set_protocol_run_status(db, protocol_run_name, ProtocolRunStatus.RUNNING)

    async def complete_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        """Complete a protocol run."""
        await self._set_protocol_run_status(db, protocol_run_name, ProtocolRunStatus.COMPLETED)

    async def cancel_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        """Cancel a protocol run."""
        await self._set_protocol_run_status(db, protocol_run_name, ProtocolRunStatus.CANCELLED)

    async def suspend_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        """Suspend a protocol run."""
        await self._set_protocol_run_status(db, protocol_run_name, ProtocolRunStatus.SUSPENDED)

    async def fail_protocol_run(
        self, db: AsyncDbSession, protocol_run_name: str, error_message: str | None = None
    ) -> None:
        """Fail a protocol run."""
        await self._set_protocol_run_status(
            db, protocol_run_name, ProtocolRunStatus.FAILED, error_message=error_message
        )

    async def get_protocol_run_priorities(self, db: AsyncDbSession, names: list[str]) -> dict[str, int]:
        if not names:
            return {}
        result = await db.execute(
            select(ProtocolRunModel.name, ProtocolRunModel.priority).where(ProtocolRunModel.name.in_(names))
        )
        return dict(result.all())

    async def fail_protocol_runs_batch(
        self, db: AsyncDbSession, names: list[str], error_message: str | None = None
    ) -> None:
        if not names:
            return
        update_fields: dict = {
            "status": ProtocolRunStatus.FAILED,
            "end_time": datetime.now(UTC),
        }
        if error_message is not None:
            update_fields["error_message"] = error_message
        await db.execute(update(ProtocolRunModel).where(ProtocolRunModel.name.in_(names)).values(**update_fields))

    async def cancel_protocol_runs_batch(self, db: AsyncDbSession, names: list[str]) -> None:
        if not names:
            return
        await db.execute(
            update(ProtocolRunModel)
            .where(ProtocolRunModel.name.in_(names))
            .values(status=ProtocolRunStatus.CANCELLED, end_time=datetime.now(UTC))
        )
