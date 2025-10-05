from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task import (
    DynamicTaskDeviceConfig,
    TaskConfig,
    TaskDeviceConfig,
)
from eos.configuration.validation import validation_utils
from eos.devices.device_manager import DeviceManager
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.allocation.allocation_manager import AllocationManager
from eos.scheduling.base_scheduler import BaseScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject
from eos.scheduling.utils import filter_device_pool, sort_resource_pool


class GreedyScheduler(BaseScheduler):
    """
    The greedy scheduler is responsible for scheduling experiment tasks based on their precedence constraints and
    required devices and resources. The scheduler uses a greedy policy, meaning that if a task is ready to be executed,
    it will be scheduled immediately pending resource availability.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        experiment_manager: ExperimentManager,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        allocation_manager: AllocationManager,
    ):
        super().__init__(configuration_manager, experiment_manager, task_manager, device_manager, allocation_manager)
        # Track device assignments for device reference resolution
        self._scheduled_device_assignments: dict[str, dict[str, dict[str, TaskDeviceConfig]]] = (
            {}
        )  # exp_name -> task_name -> device_name -> TaskDeviceConfig
        log.debug("Greedy scheduler initialized.")

    async def request_tasks(self, db: AsyncDbSession, experiment_name: str) -> list[ScheduledTask]:
        """Request the next tasks to be executed for a specific experiment."""
        # Snapshot: verify registration and capture graph outside DB I/O heavy section
        async with self._lock:
            if experiment_name not in self._registered_experiments:
                raise EosSchedulerRegistrationError(
                    f"Cannot request tasks from the scheduler for unregistered experiment {experiment_name}."
                )
            _experiment_graph = self._registered_experiments[experiment_name][1]
            _all_tasks = _experiment_graph.get_topologically_sorted_tasks()

        # DB read outside lock
        completed_tasks = await self._experiment_manager.get_completed_tasks(db, experiment_name)
        pending_tasks = [t for t in _all_tasks if t not in completed_tasks]

        # Mutations + allocation interactions under lock
        async with self._lock:
            await self._release_completed_allocations(db, {experiment_name: set(completed_tasks)})

            scheduled_tasks: list[ScheduledTask] = []
            for task_name in pending_tasks:
                scheduled_task = await self._check_and_allocate_resources(
                    db, experiment_name, task_name, completed_tasks, _experiment_graph
                )
                if scheduled_task:
                    scheduled_tasks.append(scheduled_task)

            return scheduled_tasks

    async def unregister_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """Unregister an experiment and clean up device assignment state."""
        await super().unregister_experiment(db, experiment_name)
        # Clean up device assignment tracking
        if experiment_name in self._scheduled_device_assignments:
            del self._scheduled_device_assignments[experiment_name]

    def _collect_specific_devices(
        self, task_config: TaskConfig
    ) -> tuple[dict[str, TaskDeviceConfig], set[tuple[str, str]]]:
        """Collect explicitly specified devices, deduplicated, returning dict and pair set."""
        chosen_pairs: set[tuple[str, str]] = set()
        assigned: dict[str, TaskDeviceConfig] = {}
        for device_name, dev in task_config.devices.items():
            if isinstance(dev, TaskDeviceConfig):
                chosen_pairs.add((dev.lab_name, dev.name))
                assigned[device_name] = dev
        return assigned, chosen_pairs

    async def _pick_first_available_device(
        self,
        db: AsyncDbSession,
        task_config: TaskConfig,
        experiment_name: str,
        device_pool: list[tuple[str, str]],
        chosen_device_pairs: set[tuple[str, str]],
    ) -> TaskDeviceConfig | None:
        """Pick the first available device from device_pool excluding chosen_device_pairs."""
        for lab_name, device_name in device_pool:
            if (lab_name, device_name) in chosen_device_pairs:
                continue
            candidate = TaskDeviceConfig(lab_name=lab_name, name=device_name)
            if await self._check_device_available(db, task_config, experiment_name, candidate):
                chosen_device_pairs.add((lab_name, device_name))
                return candidate
        return None

    async def _build_assigned_devices(
        self, db: AsyncDbSession, experiment_name: str, task_config: TaskConfig
    ) -> dict[str, TaskDeviceConfig] | None:
        """Greedily pick concrete devices for dynamic requirements, plus specific ones."""
        assigned_devices, chosen_device_pairs = self._collect_specific_devices(task_config)

        # Resolve device references first
        for device_name, device_value in task_config.devices.items():
            if isinstance(device_value, str) and validation_utils.is_device_reference(device_value):
                ref_task_name, ref_device_name = device_value.split(".")

                # Look up the device from previously scheduled tasks
                if (
                    experiment_name in self._scheduled_device_assignments
                    and ref_task_name in self._scheduled_device_assignments[experiment_name]
                    and ref_device_name in self._scheduled_device_assignments[experiment_name][ref_task_name]
                ):

                    resolved_device = self._scheduled_device_assignments[experiment_name][ref_task_name][
                        ref_device_name
                    ]
                    assigned_devices[device_name] = resolved_device
                    chosen_device_pairs.add((resolved_device.lab_name, resolved_device.name))
                else:
                    # Referenced device not found or task not scheduled yet
                    return None

        eligible_devices_by_type = await self._active_devices_by_type(db)

        for device_name, req in task_config.devices.items():
            if not isinstance(req, DynamicTaskDeviceConfig):
                continue

            device_pool = filter_device_pool(req, eligible_devices_by_type.get(req.device_type, []))
            if not device_pool:
                return None

            selected_device = await self._pick_first_available_device(
                db, task_config, experiment_name, device_pool, chosen_device_pairs
            )
            if not selected_device:
                return None
            assigned_devices[device_name] = selected_device

        return assigned_devices

    async def _resolve_specific_resources(
        self, db: AsyncDbSession, experiment_name: str, task_config: TaskConfig
    ) -> tuple[dict[str, str], set[str]] | None:
        """Resolve specifically-named resources; ensure availability and no duplicates."""
        resolved: dict[str, str] = {}
        chosen: set[str] = set()

        for name, value in task_config.resources.items():
            if not isinstance(value, str):
                continue
            if value in chosen:
                # skip duplicates within the same task definition
                continue
            if not await self._check_resource_available(db, task_config, experiment_name, value):
                return None
            resolved[name] = value
            chosen.add(value)

        return resolved, chosen

    async def _pick_first_available_resource(
        self,
        db: AsyncDbSession,
        task_config: TaskConfig,
        experiment_name: str,
        pool: list[str],
        chosen: set[str],
    ) -> str | None:
        """Pick the first available resource from a sorted pool, avoiding `chosen`."""
        for resource_name in pool:
            if resource_name in chosen:
                continue
            if await self._check_resource_available(db, task_config, experiment_name, resource_name):
                chosen.add(resource_name)
                return resource_name
        return None

    async def _build_resolved_resources(
        self, db: AsyncDbSession, experiment_name: str, task_config: TaskConfig
    ) -> dict[str, str] | None:
        """Resolve task resources by choosing concrete names for any dynamic requests.

        Returns a mapping resource_input_name -> resource_name, or None if requirements can't be met now.
        """
        resources_by_type = self._resources_by_type()

        # First resolve specific resources
        specific = await self._resolve_specific_resources(db, experiment_name, task_config)
        if specific is None:
            return None
        resolved, chosen = specific

        # Resolve dynamic resources
        for name, value in task_config.resources.items():
            if isinstance(value, str):
                continue

            resource_pool = resources_by_type.get(value.resource_type, [])
            filtered_pool = sort_resource_pool(resource_pool)
            if not filtered_pool:
                return None

            selected = await self._pick_first_available_resource(
                db, task_config, experiment_name, filtered_pool, chosen
            )
            if not selected:
                return None

            resolved[name] = selected

        return resolved

    async def _finalize_scheduling(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task_name: str,
        task_config: TaskConfig,
        assigned_devices: dict[str, TaskDeviceConfig],
    ) -> ScheduledTask | None:
        """
        Override to persist device assignments after successful scheduling for reference resolution.
        """
        scheduled = await super()._finalize_scheduling(db, experiment_name, task_name, task_config, assigned_devices)
        if scheduled:
            if experiment_name not in self._scheduled_device_assignments:
                self._scheduled_device_assignments[experiment_name] = {}
            self._scheduled_device_assignments[experiment_name][task_name] = assigned_devices
        return scheduled
