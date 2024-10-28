import asyncio
from datetime import datetime, timezone
from typing import Any

from eos.configuration.configuration_manager import ConfigurationManager
from eos.experiments.entities.experiment import Experiment, ExperimentStatus, ExperimentDefinition
from eos.experiments.exceptions import EosExperimentStateError
from eos.experiments.repositories.experiment_repository import ExperimentRepository
from eos.logging.logger import log
from eos.persistence.async_mongodb_interface import AsyncMongoDbInterface
from eos.tasks.repositories.task_repository import TaskRepository


class ExperimentManager:
    """
    Responsible for managing the state of all experiments in EOS and tracking their execution.
    """

    def __init__(self, configuration_manager: ConfigurationManager, db_interface: AsyncMongoDbInterface):
        self._configuration_manager = configuration_manager
        self._session_factory = db_interface.session_factory
        self._experiments = None
        self._tasks = None

    async def initialize(self, db_interface: AsyncMongoDbInterface) -> None:
        self._experiments = ExperimentRepository(db_interface)
        await self._experiments.initialize()

        self._tasks = TaskRepository(db_interface)
        await self._tasks.initialize()
        log.debug("Experiment manager initialized.")

    async def create_experiment(
        self,
        definition: ExperimentDefinition,
    ) -> None:
        """
        Create a new experiment from a definition.
        """
        experiment_id = definition.id
        experiment_type = definition.type

        if await self._experiments.exists(id=experiment_id):
            raise EosExperimentStateError(f"Experiment '{experiment_id}' already exists.")

        experiment_config = self._configuration_manager.experiments.get(experiment_type)
        if not experiment_config:
            raise EosExperimentStateError(f"Experiment type '{experiment_type}' not found in the configuration.")

        experiment = Experiment.from_definition(definition)
        await self._experiments.create(experiment.model_dump())

        log.info(f"Created experiment '{experiment_id}'.")

    async def delete_experiment(self, experiment_id: str) -> None:
        """
        Delete an experiment.
        """
        if not await self._experiments.exists(id=experiment_id):
            raise EosExperimentStateError(f"Experiment '{experiment_id}' does not exist.")

        await self._experiments.delete_one(id=experiment_id)
        await self._tasks.delete_many(experiment_id=experiment_id)

        log.info(f"Deleted experiment '{experiment_id}'.")

    async def start_experiment(self, experiment_id: str) -> None:
        """
        Start an experiment.
        """
        await self._set_experiment_status(experiment_id, ExperimentStatus.RUNNING)

    async def complete_experiment(self, experiment_id: str) -> None:
        """
        Complete an experiment.
        """
        await self._set_experiment_status(experiment_id, ExperimentStatus.COMPLETED)

    async def cancel_experiment(self, experiment_id: str) -> None:
        """
        Cancel an experiment.
        """
        await self._set_experiment_status(experiment_id, ExperimentStatus.CANCELLED)

    async def suspend_experiment(self, experiment_id: str) -> None:
        """
        Suspend an experiment.
        """
        await self._set_experiment_status(experiment_id, ExperimentStatus.SUSPENDED)

    async def fail_experiment(self, experiment_id: str) -> None:
        """
        Fail an experiment.
        """
        await self._set_experiment_status(experiment_id, ExperimentStatus.FAILED)

    async def get_experiment(self, experiment_id: str) -> Experiment | None:
        """
        Get an experiment.
        """
        experiment = await self._experiments.get_one(id=experiment_id)
        return Experiment(**experiment) if experiment else None

    async def get_experiments(self, **query: dict[str, Any]) -> list[Experiment]:
        """
        Get experiments with a custom query.

        :param query: Dictionary of query parameters.
        """
        experiments = await self._experiments.get_all(**query)
        return [Experiment(**experiment) for experiment in experiments]

    async def get_lab_experiments(self, lab: str) -> list[Experiment]:
        """
        Get all experiments associated with a lab.
        """
        experiments = await self._experiments.get_experiments_by_lab(lab)
        return [Experiment(**experiment) for experiment in experiments]

    async def get_running_tasks(self, experiment_id: str | None) -> set[str]:
        """
        Get the list of currently running tasks constrained by experiment ID.
        """
        experiment = await self._experiments.get_one(id=experiment_id)
        return set(experiment.get("running_tasks", {})) if experiment else {}

    async def get_completed_tasks(self, experiment_id: str) -> set[str]:
        """
        Get the list of completed tasks constrained by experiment ID.
        """
        experiment = await self._experiments.get_one(id=experiment_id)
        return set(experiment.get("completed_tasks", {})) if experiment else {}

    async def delete_non_completed_tasks(self, experiment_id: str) -> None:
        """
        Delete all tasks that are not completed in the given experiment.
        """
        experiment = await self.get_experiment(experiment_id)

        async with self._session_factory() as session:
            await asyncio.gather(
                self._tasks.delete_running_tasks(experiment_id, experiment.running_tasks, session=session),
                self._experiments.clear_running_tasks(experiment_id, session=session),
                self._tasks.delete_failed_and_cancelled_tasks(experiment_id, session=session),
            )
            await session.commit_transaction()

    async def _set_experiment_status(self, experiment_id: str, new_status: ExperimentStatus) -> None:
        """
        Set the status of an experiment.
        """
        if not await self._experiments.exists(id=experiment_id):
            raise EosExperimentStateError(f"Experiment '{experiment_id}' does not exist.")

        update_fields = {"status": new_status.value}
        if new_status == ExperimentStatus.RUNNING:
            update_fields["start_time"] = datetime.now(tz=timezone.utc)
        elif new_status in [
            ExperimentStatus.COMPLETED,
            ExperimentStatus.CANCELLED,
            ExperimentStatus.FAILED,
        ]:
            update_fields["end_time"] = datetime.now(tz=timezone.utc)

        await self._experiments.update_one(update_fields, id=experiment_id)
