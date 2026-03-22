from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import (
    DynamicDeviceAssignmentDef,
    TaskDef,
    DeviceAssignmentDef,
)
from eos.configuration.utils import is_device_reference
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
    """Greedy scheduler: schedules tasks immediately when dependencies are met and resources available."""

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
        # Track device assignments for reference resolution
        self._scheduled_device_assignments: dict[str, dict[str, dict[str, DeviceAssignmentDef]]] = {}
        log.debug("Greedy scheduler initialized.")

    async def request_tasks(self, db: AsyncDbSession, experiment_name: str) -> list[ScheduledTask]:
        async with self._lock:
            self._clear_per_cycle_caches()
            if experiment_name not in self._registered_experiments:
                raise EosSchedulerRegistrationError(
                    f"Cannot request tasks from the scheduler for unregistered experiment {experiment_name}."
                )
            _experiment_graph = self._registered_experiments[experiment_name][1]
            _all_tasks = self._topo_sorted_cache[experiment_name]

        completed_tasks = self._completed_tasks_cache.pop(experiment_name, None)
        if completed_tasks is None:
            completed_tasks = await self._experiment_manager.get_completed_tasks(db, experiment_name)
        pending_tasks = [t for t in _all_tasks if t not in completed_tasks]

        async with self._lock:
            try:
                self._current_completed_tasks = completed_tasks
                await self._release_completed_allocations(db, {experiment_name: set(completed_tasks)})

                scheduled_tasks: list[ScheduledTask] = []
                for task_name in pending_tasks:
                    scheduled_task = await self._check_and_allocate_resources(
                        db, experiment_name, task_name, completed_tasks, _experiment_graph
                    )
                    if scheduled_task:
                        scheduled_tasks.append(scheduled_task)

                return scheduled_tasks
            finally:
                self._current_completed_tasks = None
                self._clear_per_cycle_caches()

    async def unregister_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        await super().unregister_experiment(db, experiment_name)
        self._scheduled_device_assignments.pop(experiment_name, None)

    # ---- Device resolution ----

    def _collect_specific_devices(self, task: TaskDef) -> tuple[dict[str, DeviceAssignmentDef], set[tuple[str, str]]]:
        chosen_pairs: set[tuple[str, str]] = set()
        assigned: dict[str, DeviceAssignmentDef] = {}
        for device_name, dev in task.devices.items():
            if isinstance(dev, DeviceAssignmentDef):
                chosen_pairs.add((dev.lab_name, dev.name))
                assigned[device_name] = dev
        return assigned, chosen_pairs

    async def _pick_first_available_device(
        self,
        db: AsyncDbSession,
        task: TaskDef,
        experiment_name: str,
        device_pool: list[tuple[str, str]],
        chosen_device_pairs: set[tuple[str, str]],
    ) -> DeviceAssignmentDef | None:
        for lab_name, device_name in device_pool:
            if (lab_name, device_name) in chosen_device_pairs:
                continue
            if not self._is_device_available(lab_name, device_name, task.name, experiment_name):
                continue
            if not await self._check_device_active(db, lab_name, device_name, task.name):
                continue
            chosen_device_pairs.add((lab_name, device_name))
            return DeviceAssignmentDef(lab_name=lab_name, name=device_name)
        return None

    async def _build_assigned_devices(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> dict[str, DeviceAssignmentDef] | None:
        assigned_devices, chosen_device_pairs = self._collect_specific_devices(task)

        # Resolve device references
        for device_name, device_value in task.devices.items():
            if isinstance(device_value, str) and is_device_reference(device_value):
                ref_task_name, ref_device_name = device_value.split(".")
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
                    return None

        eligible_devices_by_type = await self._active_devices_by_type(db)

        for device_name, req in task.devices.items():
            if not isinstance(req, DynamicDeviceAssignmentDef):
                continue

            device_pool = filter_device_pool(req, eligible_devices_by_type.get(req.device_type, []))
            if not device_pool:
                log.warning(
                    "No devices of type '%s' found for task '%s' in experiment '%s'.",
                    req.device_type,
                    task.name,
                    experiment_name,
                )
                return None

            selected_device = await self._pick_first_available_device(
                db, task, experiment_name, device_pool, chosen_device_pairs
            )
            if not selected_device:
                return None
            assigned_devices[device_name] = selected_device

        return assigned_devices

    # ---- Resource resolution ----

    async def _resolve_specific_resources(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> tuple[dict[str, str], set[str]] | None:
        resolved: dict[str, str] = {}
        chosen: set[str] = set()

        for name, value in task.resources.items():
            if not isinstance(value, str):
                continue
            if value in chosen:
                continue
            if not self._is_resource_available(value, task.name, experiment_name):
                return None
            resolved[name] = value
            chosen.add(value)

        return resolved, chosen

    async def _pick_first_available_resource(
        self, db: AsyncDbSession, task: TaskDef, experiment_name: str, pool: list[str], chosen: set[str]
    ) -> str | None:
        for resource_name in pool:
            if resource_name in chosen:
                continue
            if self._is_resource_available(resource_name, task.name, experiment_name):
                chosen.add(resource_name)
                return resource_name
        return None

    async def _build_resolved_resources(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> dict[str, str] | None:
        resources_by_type = self._resources_by_type()

        specific = await self._resolve_specific_resources(db, experiment_name, task)
        if specific is None:
            return None
        resolved, chosen = specific

        for name, value in task.resources.items():
            if isinstance(value, str):
                continue

            resource_pool = resources_by_type.get(value.resource_type, [])
            filtered_pool = sort_resource_pool(resource_pool)
            if not filtered_pool:
                return None

            selected = await self._pick_first_available_resource(db, task, experiment_name, filtered_pool, chosen)
            if not selected:
                return None
            resolved[name] = selected

        return resolved

    # ---- Override finalize to track device assignments ----

    async def _finalize_scheduling(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task_name: str,
        task: TaskDef,
        assigned_devices: dict[str, DeviceAssignmentDef],
        completed_tasks: set[str] | None = None,
    ) -> ScheduledTask | None:
        scheduled = await super()._finalize_scheduling(
            db, experiment_name, task_name, task, assigned_devices, completed_tasks
        )
        if scheduled:
            self._scheduled_device_assignments.setdefault(experiment_name, {})[task_name] = assigned_devices
        return scheduled
