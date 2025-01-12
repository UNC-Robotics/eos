from datetime import datetime, timezone
from typing import Any

from sqlalchemy import exists, select, Select, delete, and_, update

from eos.configuration.configuration_manager import ConfigurationManager
from eos.experiments.entities.experiment import Experiment, ExperimentStatus, ExperimentDefinition, ExperimentModel
from eos.experiments.exceptions import EosExperimentStateError
from eos.logging.logger import log

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import TaskModel, TaskStatus
from eos.utils.di.di_container import inject_all


class ExperimentManager:
    """
    Responsible for managing the state of all experiments in EOS and tracking their execution.
    """

    @inject_all
    def __init__(self, configuration_manager: ConfigurationManager):
        self._configuration_manager = configuration_manager
        log.debug("Experiment manager initialized.")

    def _get_experiment_exists_query(self, experiment_id: str) -> Select:
        """Create a reusable exists query for experiment validation."""
        return select(exists().where(ExperimentModel.id == experiment_id))

    async def _check_experiment_exists(self, db: AsyncDbSession, experiment_id: str) -> bool:
        """Check if an experiment exists."""
        result = await db.execute(self._get_experiment_exists_query(experiment_id))
        return bool(result.scalar())

    async def _validate_experiment_exists(self, db: AsyncDbSession, experiment_id: str) -> None:
        """Validate experiment existence or raise an error."""
        if not await self._check_experiment_exists(db, experiment_id):
            raise EosExperimentStateError(f"Experiment '{experiment_id}' does not exist.")

    async def create_experiment(self, db: AsyncDbSession, definition: ExperimentDefinition) -> None:
        """Create a new experiment from a definition."""
        if await self._check_experiment_exists(db, definition.id):
            raise EosExperimentStateError(
                f"Experiment '{definition.id}' already exists. Please create an experiment with a different id."
            )

        experiment_config = self._configuration_manager.experiments.get(definition.type)
        if not experiment_config:
            raise EosExperimentStateError(f"Experiment type '{definition.type}' not found in the configuration.")

        experiment = Experiment.from_definition(definition)
        experiment_model = ExperimentModel(**experiment.model_dump())

        db.add(experiment_model)
        await db.flush()

        log.info(f"Created experiment '{definition.id}'.")

    async def delete_experiment(self, db: AsyncDbSession, experiment_id: str) -> None:
        """Delete an experiment and its associated tasks."""
        await self._validate_experiment_exists(db, experiment_id)

        # Delete associated tasks first
        await db.execute(delete(TaskModel).where(TaskModel.experiment_id == experiment_id))
        await db.execute(delete(ExperimentModel).where(ExperimentModel.id == experiment_id))

        log.info(f"Deleted experiment '{experiment_id}'.")

    async def get_experiment(self, db: AsyncDbSession, experiment_id: str) -> Experiment | None:
        """Get an experiment by ID."""
        result = await db.execute(select(ExperimentModel).where(ExperimentModel.id == experiment_id))
        if experiment_model := result.scalar_one_or_none():
            return Experiment.model_validate(experiment_model)
        return None

    async def get_experiments(self, db: AsyncDbSession, **filters: Any) -> list[Experiment]:
        """Query experiments with arbitrary parameters."""
        stmt = select(ExperimentModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(ExperimentModel, key) == value)

        result = await db.execute(stmt)
        return [Experiment.model_validate(model) for model in result.scalars()]

    async def get_running_tasks(self, db: AsyncDbSession, experiment_id: str | None) -> set[str]:
        """Get the set of currently running task IDs for an experiment."""
        result = await db.execute(select(ExperimentModel.running_tasks).where(ExperimentModel.id == experiment_id))
        if tasks := result.scalar_one_or_none():
            return set(tasks)
        return set()

    async def get_completed_tasks(self, db: AsyncDbSession, experiment_id: str) -> set[str]:
        """Get the set of completed task IDs for an experiment."""
        result = await db.execute(select(ExperimentModel.completed_tasks).where(ExperimentModel.id == experiment_id))
        if tasks := result.scalar_one_or_none():
            return set(tasks)
        return set()

    async def delete_non_completed_tasks(self, db: AsyncDbSession, experiment_id: str) -> None:
        """Delete running, failed and cancelled tasks for an experiment."""
        experiment = await self.get_experiment(db, experiment_id)
        if not experiment:
            raise EosExperimentStateError(f"Experiment '{experiment_id}' does not exist.")

        # Delete running tasks
        if experiment.running_tasks:
            await db.execute(
                delete(TaskModel).where(
                    and_(TaskModel.experiment_id == experiment_id, TaskModel.id.in_(experiment.running_tasks))
                )
            )

        # Clear running tasks list in experiment
        await db.execute(update(ExperimentModel).where(ExperimentModel.id == experiment_id).values(running_tasks=[]))

        # Delete failed and cancelled tasks
        await db.execute(
            delete(TaskModel).where(
                and_(
                    TaskModel.experiment_id == experiment_id,
                    TaskModel.status.in_([TaskStatus.FAILED, TaskStatus.CANCELLED]),
                )
            )
        )

    async def _set_experiment_status(
        self, db: AsyncDbSession, experiment_id: str, new_status: ExperimentStatus
    ) -> None:
        """Set the status of an experiment."""
        await self._validate_experiment_exists(db, experiment_id)

        update_fields = {"status": new_status}
        if new_status == ExperimentStatus.RUNNING:
            update_fields["start_time"] = datetime.now(timezone.utc)
        elif new_status in [
            ExperimentStatus.COMPLETED,
            ExperimentStatus.CANCELLED,
            ExperimentStatus.FAILED,
        ]:
            update_fields["end_time"] = datetime.now(timezone.utc)

        await db.execute(update(ExperimentModel).where(ExperimentModel.id == experiment_id).values(**update_fields))

    async def start_experiment(self, db: AsyncDbSession, experiment_id: str) -> None:
        """Start an experiment."""
        await self._set_experiment_status(db, experiment_id, ExperimentStatus.RUNNING)

    async def complete_experiment(self, db: AsyncDbSession, experiment_id: str) -> None:
        """Complete an experiment."""
        await self._set_experiment_status(db, experiment_id, ExperimentStatus.COMPLETED)

    async def cancel_experiment(self, db: AsyncDbSession, experiment_id: str) -> None:
        """Cancel an experiment."""
        await self._set_experiment_status(db, experiment_id, ExperimentStatus.CANCELLED)

    async def suspend_experiment(self, db: AsyncDbSession, experiment_id: str) -> None:
        """Suspend an experiment."""
        await self._set_experiment_status(db, experiment_id, ExperimentStatus.SUSPENDED)

    async def fail_experiment(self, db: AsyncDbSession, experiment_id: str) -> None:
        """Fail an experiment."""
        await self._set_experiment_status(db, experiment_id, ExperimentStatus.FAILED)
