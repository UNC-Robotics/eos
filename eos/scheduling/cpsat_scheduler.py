import asyncio

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import DynamicDeviceAssignmentDef, TaskDef, DeviceAssignmentDef
from eos.configuration.experiment_graph import ExperimentGraph
from eos.devices.device_manager import DeviceManager
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.allocation.allocation_manager import AllocationManager
from eos.scheduling.base_scheduler import BaseScheduler
from eos.scheduling.cpsat_scheduling_solver import CpSatSchedulingSolver
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject


class CpSatScheduler(BaseScheduler):
    """Global scheduler using CP-SAT with makespan then start-time minimization."""

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
        self._schedule: dict[str, dict[str, int]] = {}
        self._schedule_is_stale = False
        self._task_durations: dict[str, dict[str, int]] = {}
        self._current_time: int = 0
        self._device_assignments: dict[str, dict[str, dict[str, DeviceAssignmentDef]]] = {}
        self._resource_assignments: dict[str, dict[str, dict[str, str]]] = {}
        self._parameter_overrides: dict[str, float | int | bool] = {}

        log.debug("CP-SAT scheduler initialized.")

    async def register_experiment(
        self, experiment_name: str, experiment_type: str, experiment_graph: ExperimentGraph
    ) -> None:
        async with self._lock:
            await super().register_experiment(experiment_name, experiment_type, experiment_graph)
            self._schedule_is_stale = True

    async def unregister_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        had_running = self._has_running_tasks(experiment_name)
        async with self._lock:
            await super().unregister_experiment(db, experiment_name)
            self._schedule.pop(experiment_name, None)
            self._device_assignments.pop(experiment_name, None)
            self._resource_assignments.pop(experiment_name, None)
            self._task_durations.pop(experiment_name, None)
            if not self._registered_experiments:
                self._current_time = 0
            elif had_running:
                self._schedule_is_stale = True

    def _has_running_tasks(self, experiment_name: str) -> bool:
        """Check if an experiment has non-held allocations (running tasks)."""
        for entry in self._device_index.values():
            if entry.experiment_name == experiment_name and not entry.held:
                return True
        for entry in self._resource_index.values():
            if entry.experiment_name == experiment_name and not entry.held:
                return True
        return False

    async def update_parameters(self, parameters: dict) -> None:
        await super().update_parameters(parameters)
        async with self._lock:
            self._parameter_overrides.update(parameters)
            self._schedule_is_stale = True

    async def _compute_schedule(self, db: AsyncDbSession) -> None:
        completed_by_exp = await self._experiment_manager.get_all_completed_tasks(
            db, list(self._registered_experiments.keys())
        )
        running_by_exp: dict[str, set[str]] = {}
        for exp_name in self._registered_experiments:
            running = set()
            for entry in self._device_index.values():
                if entry.experiment_name == exp_name and not entry.held:
                    running.add(entry.owner)
            for entry in self._resource_index.values():
                if entry.experiment_name == exp_name and not entry.held:
                    running.add(entry.owner)
            running_by_exp[exp_name] = running

        experiment_names = list(self._registered_experiments.keys())
        experiment_priorities = await self._get_experiment_priorities(db, experiment_names)
        eligible_devices_by_type = await self._active_devices_by_type(db)
        eligible_resources_by_type = self._resources_by_type_with_labs()

        solver = CpSatSchedulingSolver(
            experiments=self._registered_experiments,
            task_durations=self._task_durations,
            schedule=self._schedule,
            completed_by_exp=completed_by_exp,
            running_by_exp=running_by_exp,
            current_time=self._current_time,
            experiment_priorities=experiment_priorities,
            eligible_devices_by_type=eligible_devices_by_type,
            eligible_resources_by_type=eligible_resources_by_type,
            previous_device_assignments=self._device_assignments,
            previous_resource_assignments=self._resource_assignments,
            parameter_overrides=self._parameter_overrides or None,
        )

        loop = asyncio.get_running_loop()
        solution = await loop.run_in_executor(None, solver.solve)

        self._schedule = solution.schedule
        self._device_assignments = solution.device_assignments
        self._resource_assignments = solution.resource_assignments

    async def request_tasks(self, db: AsyncDbSession, experiment_name: str) -> list[ScheduledTask]:
        self._clear_per_cycle_caches()
        if experiment_name not in self._registered_experiments:
            raise EosSchedulerRegistrationError(f"Experiment {experiment_name} is not registered.")

        all_completed_by_exp = await self._experiment_manager.get_all_completed_tasks(
            db, list(self._registered_experiments.keys())
        )
        completed_tasks = all_completed_by_exp.get(experiment_name, set())

        async with self._lock:
            try:
                self._current_completed_tasks = completed_tasks
                await self._release_completed_allocations(db, all_completed_by_exp)

                max_end_time = max(
                    [0]
                    + [
                        self._schedule[exp_name][task_name] + self._task_durations[exp_name][task_name]
                        for exp_name, completed in all_completed_by_exp.items()
                        for task_name in completed
                        if exp_name in self._schedule
                        and task_name in self._schedule[exp_name]
                        and exp_name in self._task_durations
                        and task_name in self._task_durations[exp_name]
                    ]
                )
                self._current_time = max(self._current_time, max_end_time)

                if self._schedule_is_stale:
                    await self._compute_schedule(db)
                    self._schedule_is_stale = False

                _, exp_graph = self._registered_experiments[experiment_name]
                all_tasks = self._topo_sorted_cache[experiment_name]

                scheduled_tasks = []
                for task_name in all_tasks:
                    if task_name in completed_tasks:
                        continue
                    if self._schedule[experiment_name][task_name] > self._current_time:
                        continue

                    scheduled_task = await self._check_and_allocate_resources(
                        db, experiment_name, task_name, completed_tasks, exp_graph
                    )
                    if scheduled_task:
                        scheduled_tasks.append(scheduled_task)

                return scheduled_tasks
            finally:
                self._current_completed_tasks = None
                self._clear_per_cycle_caches()

    async def _build_assigned_devices(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> dict[str, DeviceAssignmentDef] | None:
        task_name = task.name
        assigned_devices: dict[str, DeviceAssignmentDef] = {}

        solver_assignments = self._device_assignments.get(experiment_name, {}).get(task_name, {})
        assigned_devices.update(solver_assignments)

        for device_name, dev in task.devices.items():
            if isinstance(dev, DeviceAssignmentDef):
                assigned_devices[device_name] = dev

        has_dynamic = any(isinstance(d, DynamicDeviceAssignmentDef) for d in task.devices.values())
        if has_dynamic and not self._device_assignments.get(experiment_name, {}).get(task_name):
            self._schedule_is_stale = True
            return None

        labs = getattr(self._configuration_manager, "labs", {})
        for dev in solver_assignments.values():
            if dev.lab_name not in labs or dev.name not in labs[dev.lab_name].devices:
                self._schedule_is_stale = True
                return None

        return assigned_devices

    async def _build_resolved_resources(
        self, db: AsyncDbSession, experiment_name: str, task: TaskDef
    ) -> dict[str, str] | None:
        task_name = task.name
        has_dynamic = any(not isinstance(v, str) for v in task.resources.values())
        assigned = self._resource_assignments.get(experiment_name, {}).get(task_name)
        if has_dynamic and not assigned:
            self._schedule_is_stale = True
            return None

        if assigned:
            labs = getattr(self._configuration_manager, "labs", {})
            all_resources = {resource_name for lab_cfg in labs.values() for resource_name in lab_cfg.resources}
            for resource_name in assigned.values():
                if resource_name not in all_resources:
                    self._schedule_is_stale = True
                    return None

        resolved: dict[str, str] = {}
        if assigned:
            resolved.update(assigned)
        for name, value in task.resources.items():
            if isinstance(value, str):
                resolved.setdefault(name, value)
        return resolved
