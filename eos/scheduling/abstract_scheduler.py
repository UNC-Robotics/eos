from abc import ABC, abstractmethod

from eos.configuration.experiment_graph import ExperimentGraph
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.entities.task import TaskSubmission


class AbstractScheduler(ABC):
    """Interface for EOS schedulers."""

    @abstractmethod
    async def register_experiment(
        self, experiment_name: str, experiment_type: str, experiment_graph: ExperimentGraph
    ) -> None:
        """Register an experiment with the scheduler."""

    @abstractmethod
    async def unregister_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Unregister an experiment and release its allocations."""

    @abstractmethod
    async def request_tasks(self, db: AsyncDbSession, experiment_name: str) -> list[ScheduledTask]:
        """Request the next tasks to be executed for a specific experiment."""

    @abstractmethod
    async def is_experiment_completed(self, db: AsyncDbSession, experiment_name: str) -> bool:
        """Check if an experiment has been completed."""

    @abstractmethod
    async def update_parameters(self, parameters: dict) -> None:
        """Update scheduler-specific parameters."""

    @abstractmethod
    async def submit_on_demand_task(self, db: AsyncDbSession, task_submission: TaskSubmission) -> ScheduledTask | None:
        """Submit an on-demand task. Returns ScheduledTask if immediately schedulable, else queues it."""

    @abstractmethod
    async def process_pending_on_demand(self, db: AsyncDbSession) -> list[tuple[TaskSubmission, ScheduledTask]]:
        """Retry queued on-demand tasks. Returns (submission, scheduled_task) pairs."""

    @abstractmethod
    async def release_task(self, db: AsyncDbSession, task_name: str, experiment_name: str | None = None) -> None:
        """Release allocations for a completed/failed task, respecting holds."""
