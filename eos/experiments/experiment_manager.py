from datetime import datetime, UTC
from typing import Any

from sqlalchemy import exists, select, delete, and_, update

from eos.configuration.configuration_manager import ConfigurationManager
from eos.experiments.entities.experiment import Experiment, ExperimentStatus, ExperimentSubmission, ExperimentModel
from eos.experiments.exceptions import EosExperimentStateError
from eos.logging.logger import log

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import TaskModel, TaskStatus
from eos.utils.di.di_container import inject


class ExperimentManager:
    """
    Responsible for managing the state of all experiments in EOS and tracking their execution.
    """

    @inject
    def __init__(self, configuration_manager: ConfigurationManager):
        self._configuration_manager = configuration_manager
        log.debug("Experiment manager initialized.")

    async def _check_experiment_exists(self, db: AsyncDbSession, experiment_name: str) -> bool:
        """Check if an experiment exists."""
        result = await db.execute(select(exists().where(ExperimentModel.name == experiment_name)))
        return bool(result.scalar())

    async def _validate_experiment_exists(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Validate experiment existence or raise an error."""
        if not await self._check_experiment_exists(db, experiment_name):
            raise EosExperimentStateError(f"Experiment '{experiment_name}' does not exist.")

    async def create_experiment(
        self, db: AsyncDbSession, submission: ExperimentSubmission, campaign: str | None = None
    ) -> None:
        """Create a new experiment from a submission."""
        if await self._check_experiment_exists(db, submission.name):
            raise EosExperimentStateError(
                f"Experiment '{submission.name}' already exists. Please create an experiment with a different name."
            )

        experiment_def = self._configuration_manager.experiments.get(submission.type)
        if not experiment_def:
            raise EosExperimentStateError(f"Experiment type '{submission.type}' not found in the configuration.")

        experiment = Experiment.from_submission(submission)
        experiment.campaign = campaign
        experiment_model = ExperimentModel(**experiment.model_dump())

        db.add(experiment_model)
        await db.flush()

        log.info(f"Created experiment '{submission.name}'.")

    async def delete_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Delete an experiment and its associated tasks."""
        await self._validate_experiment_exists(db, experiment_name)

        # Delete associated tasks first
        await db.execute(delete(TaskModel).where(TaskModel.experiment_name == experiment_name))
        await db.execute(delete(ExperimentModel).where(ExperimentModel.name == experiment_name))

        log.info(f"Deleted experiment '{experiment_name}'.")

    async def get_experiment(self, db: AsyncDbSession, experiment_name: str) -> Experiment | None:
        """Get an experiment by name."""
        result = await db.execute(select(ExperimentModel).where(ExperimentModel.name == experiment_name))
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

    async def get_running_tasks(self, db: AsyncDbSession, experiment_name: str | None) -> set[str]:
        """Get the set of currently running task names for an experiment."""
        result = await db.execute(
            select(TaskModel.name).where(
                and_(TaskModel.experiment_name == experiment_name, TaskModel.status == TaskStatus.RUNNING)
            )
        )
        return {task_name for (task_name,) in result.all()}

    async def get_completed_tasks(self, db: AsyncDbSession, experiment_name: str) -> set[str]:
        """Get the set of completed task names for an experiment."""
        result = await db.execute(
            select(TaskModel.name).where(
                and_(TaskModel.experiment_name == experiment_name, TaskModel.status == TaskStatus.COMPLETED)
            )
        )
        return {task_name for (task_name,) in result.all()}

    async def get_all_completed_tasks(self, db: AsyncDbSession, experiment_names: list[str]) -> dict[str, set[str]]:
        """
        Get completed tasks for all experiments in the provided list.
        Returns a dictionary mapping experiment_name to a set of completed task names.
        """
        result = await db.execute(
            select(TaskModel.experiment_name, TaskModel.name).where(
                and_(TaskModel.experiment_name.in_(experiment_names), TaskModel.status == TaskStatus.COMPLETED)
            )
        )

        completed_mapping = {}
        for exp_name, task_name in result.all():
            if exp_name not in completed_mapping:
                completed_mapping[exp_name] = set()
            completed_mapping[exp_name].add(task_name)

        # Ensure all experiment_names are present in the result
        for exp_name in experiment_names:
            completed_mapping.setdefault(exp_name, set())
        return completed_mapping

    async def get_all_running_tasks(self, db: AsyncDbSession, experiment_names: list[str]) -> dict[str, set[str]]:
        """
        Get running tasks for all experiments in the provided list.
        Returns a dictionary mapping experiment_name to a set of running task names.
        """
        result = await db.execute(
            select(TaskModel.experiment_name, TaskModel.name).where(
                and_(TaskModel.experiment_name.in_(experiment_names), TaskModel.status == TaskStatus.RUNNING)
            )
        )

        running_mapping = {}
        for exp_name, task_name in result.all():
            if exp_name not in running_mapping:
                running_mapping[exp_name] = set()
            running_mapping[exp_name].add(task_name)

        # Ensure all experiment_names are present in the result
        for exp_name in experiment_names:
            running_mapping.setdefault(exp_name, set())
        return running_mapping

    async def delete_non_completed_tasks(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Delete running, failed and cancelled tasks for an experiment."""
        await self._validate_experiment_exists(db, experiment_name)

        # Delete non-completed tasks (running, failed, cancelled)
        await db.execute(
            delete(TaskModel).where(
                and_(
                    TaskModel.experiment_name == experiment_name,
                    TaskModel.status.in_([TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED]),
                )
            )
        )

    async def _set_experiment_status(
        self, db: AsyncDbSession, experiment_name: str, new_status: ExperimentStatus
    ) -> None:
        """Set the status of an experiment."""
        await self._validate_experiment_exists(db, experiment_name)

        update_fields = {"status": new_status}
        if new_status == ExperimentStatus.RUNNING:
            update_fields["start_time"] = datetime.now(UTC)
        elif new_status in [
            ExperimentStatus.COMPLETED,
            ExperimentStatus.CANCELLED,
            ExperimentStatus.FAILED,
        ]:
            update_fields["end_time"] = datetime.now(UTC)

        await db.execute(update(ExperimentModel).where(ExperimentModel.name == experiment_name).values(**update_fields))

    async def start_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Start an experiment."""
        await self._set_experiment_status(db, experiment_name, ExperimentStatus.RUNNING)

    async def complete_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Complete an experiment."""
        await self._set_experiment_status(db, experiment_name, ExperimentStatus.COMPLETED)

    async def cancel_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Cancel an experiment."""
        await self._set_experiment_status(db, experiment_name, ExperimentStatus.CANCELLED)

    async def suspend_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Suspend an experiment."""
        await self._set_experiment_status(db, experiment_name, ExperimentStatus.SUSPENDED)

    async def fail_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Fail an experiment."""
        await self._set_experiment_status(db, experiment_name, ExperimentStatus.FAILED)
