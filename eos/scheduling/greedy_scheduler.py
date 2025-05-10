import asyncio

from eos.configuration.configuration_manager import ConfigurationManager
from eos.devices.device_manager import DeviceManager
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.resource_allocation.resource_allocation_manager import ResourceAllocationManager
from eos.scheduling.base_scheduler import BaseScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject


class GreedyScheduler(BaseScheduler):
    """
    The greedy scheduler is responsible for scheduling experiment tasks based on their precedence constraints and
    required devices and containers. The scheduler uses a greedy policy, meaning that if a task is ready to be executed,
    it will be scheduled immediately pending resource availability.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        experiment_manager: ExperimentManager,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        resource_allocation_manager: ResourceAllocationManager,
    ):
        super().__init__(
            configuration_manager, experiment_manager, task_manager, device_manager, resource_allocation_manager
        )
        log.debug("Greedy scheduler initialized.")

    async def request_tasks(self, db: AsyncDbSession, experiment_id: str) -> list[ScheduledTask]:
        """Request the next tasks to be executed for a specific experiment."""
        async with self._lock:
            if experiment_id not in self._registered_experiments:
                raise EosSchedulerRegistrationError(
                    f"Cannot request tasks from the scheduler for unregistered experiment {experiment_id}."
                )
            experiment_type, experiment_graph = self._registered_experiments[experiment_id]

            all_tasks = experiment_graph.get_topologically_sorted_tasks()
            completed_tasks = await self._experiment_manager.get_completed_tasks(db, experiment_id)
            pending_tasks = [task_id for task_id in all_tasks if task_id not in completed_tasks]

            # Release resources for completed tasks
            allocated_tasks = set(self._allocated_resources.get(experiment_id, {}))
            tasks_to_release = completed_tasks.intersection(allocated_tasks)
            await asyncio.gather(
                *(self._release_task_resources(db, experiment_id, task_id) for task_id in tasks_to_release)
            )

            scheduled_tasks = []
            for task_id in pending_tasks:
                scheduled_task = await self._check_and_allocate_resources(
                    db, experiment_id, task_id, completed_tasks, experiment_graph
                )
                if scheduled_task:
                    scheduled_tasks.append(scheduled_task)

            return scheduled_tasks
