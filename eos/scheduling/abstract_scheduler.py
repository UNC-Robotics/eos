from abc import ABC, abstractmethod

from eos.configuration.experiment_graph import ExperimentGraph
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.scheduling.entities.scheduled_task import ScheduledTask


class AbstractScheduler(ABC):
    @abstractmethod
    async def register_experiment(
        self, experiment_name: str, experiment_type: str, experiment_graph: ExperimentGraph
    ) -> None:
        """
        Register an experiment with the scheduler.

        :param experiment_name: The name of the experiment.
        :param experiment_type: The type of the experiment.
        :param experiment_graph: The task graph of the experiment.
        """

    @abstractmethod
    async def unregister_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """
        Unregister an experiment from the scheduler.

        :param db: A database session.
        :param experiment_name: The name of the experiment.
        """

    @abstractmethod
    async def request_tasks(self, db: AsyncDbSession, experiment_name: str) -> list[ScheduledTask]:
        """
        Request the next tasks to be executed for a specific experiment.

        :param db: A database session.
        :param experiment_name: The name of the experiment.
        :return: A list of tasks to be executed next. Returns an empty list if no new tasks are available.
        """

    @abstractmethod
    async def is_experiment_completed(self, db: AsyncDbSession, experiment_name: str) -> bool:
        """
        Check if an experiment has been completed.

        :param db: A database session.
        :param experiment_name: The name of the experiment.
        :return: True if the experiment has been completed, False otherwise.
        """

    @abstractmethod
    async def update_parameters(self, parameters: dict) -> None:
        """
        Update scheduler-specific parameters.

        :param parameters: Dictionary of parameter names and values to update.
        :return: None
        """
