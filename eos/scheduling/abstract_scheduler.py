from abc import ABC, abstractmethod
from typing import NamedTuple

from eos.configuration.protocol_graph import ProtocolGraph
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.entities.task import TaskSubmission

# Re-check at least this often even when no tracked scheduling state changed (e.g. a device was re-enabled)
SCHEDULER_POLL_INTERVAL = 1.0  # seconds


class OnDemandProgress(NamedTuple):
    scheduled: list[tuple[TaskSubmission, ScheduledTask]]
    timed_out: list[TaskSubmission]


class AbstractScheduler(ABC):
    """Interface for EOS schedulers."""

    @abstractmethod
    async def register_protocol_run(self, protocol_run_name: str, protocol: str, protocol_graph: ProtocolGraph) -> None:
        """Register a protocol run with the scheduler."""

    @abstractmethod
    async def unregister_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        """Unregister a protocol run and release its allocations."""

    @property
    @abstractmethod
    def state_version(self) -> int:
        """A counter that changes whenever scheduling state changes, so callers can skip requests that cannot help."""

    @abstractmethod
    async def request_tasks(self, db: AsyncDbSession, protocol_run_name: str) -> list[ScheduledTask]:
        """Request the next tasks to be executed for a specific protocol run."""

    @abstractmethod
    async def is_protocol_run_completed(self, db: AsyncDbSession, protocol_run_name: str) -> bool:
        """Check if a protocol run has been completed."""

    @abstractmethod
    async def update_parameters(self, parameters: dict) -> None:
        """Update scheduler-specific parameters."""

    @abstractmethod
    async def submit_on_demand_task(self, db: AsyncDbSession, task_submission: TaskSubmission) -> ScheduledTask | None:
        """Submit an on-demand task. Returns ScheduledTask if immediately schedulable, else queues it."""

    @abstractmethod
    async def process_pending_on_demand(self, db: AsyncDbSession) -> OnDemandProgress:
        """Retry queued on-demand tasks. Returns the newly scheduled and the timed out ones."""

    @abstractmethod
    async def cancel_on_demand_task(self, task_name: str) -> bool:
        """Remove a queued on-demand task. Returns whether it was queued."""

    @abstractmethod
    async def release_task(self, db: AsyncDbSession, task_name: str, protocol_run_name: str | None = None) -> None:
        """Release allocations for a completed/failed task, respecting holds."""
