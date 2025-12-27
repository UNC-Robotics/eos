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
        async with self._lock:
            await super().unregister_experiment(db, experiment_name)

            # Remove experiment data
            self._schedule_is_stale = True
            self._schedule.pop(experiment_name, None)
            self._device_assignments.pop(experiment_name, None)
            self._resource_assignments.pop(experiment_name, None)
            self._task_durations.pop(experiment_name, None)

            # Reset current_time if no experiments remain
            if not self._registered_experiments:
                self._current_time = 0

    async def update_parameters(self, parameters: dict) -> None:
        """Update cp-sat solver parameters at runtime (e.g., num_search_workers, random_seed)."""
        # Let base tune caches / invalidation first
        await super().update_parameters(parameters)
        async with self._lock:
            self._parameter_overrides.update(parameters)
            self._schedule_is_stale = True

    async def _compute_schedule(self, db: AsyncDbSession) -> None:
        """Solve two-phase model and extract start times and dynamic device choices."""
        completed_by_exp = await self._experiment_manager.get_all_completed_tasks(
            db, list(self._registered_experiments.keys())
        )
        running_by_exp = {
            exp_name: set(self._allocated_resources.get(exp_name, {}).keys())
            for exp_name in self._registered_experiments
        }

        # Build a dictionary mapping experiment IDs to their priority
        experiment_names = list(self._registered_experiments.keys())
        experiment_priorities = await self._get_experiment_priorities(db, experiment_names)

        # Gather active devices and resources by type for dynamic allocation
        eligible_devices_by_type = await self._active_devices_by_type(db)
        eligible_resources_by_type = self._resources_by_type_with_labs()

        # Create and run the CP-SAT solver
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

        # Update scheduler state with the solution
        self._schedule = solution.schedule
        self._device_assignments = solution.device_assignments
        self._resource_assignments = solution.resource_assignments

    async def request_tasks(self, db: AsyncDbSession, experiment_name: str) -> list[ScheduledTask]:
        """Return ready tasks: deps done, scheduled <= now, and resources available."""
        if experiment_name not in self._registered_experiments:
            raise EosSchedulerRegistrationError(f"Experiment {experiment_name} is not registered.")

        # DB read outside lock
        all_completed_by_exp = await self._experiment_manager.get_all_completed_tasks(
            db, list(self._registered_experiments.keys())
        )
        completed_tasks = all_completed_by_exp.get(experiment_name, set())

        async with self._lock:
            # Release allocations for completed tasks under lock (mutates scheduler state)
            await self._release_completed_allocations(db, all_completed_by_exp)

            # Compute the global current time from all completed tasks across experiments
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

            # Process tasks for the given experiment
            _, exp_graph = self._registered_experiments[experiment_name]
            all_tasks = exp_graph.get_topologically_sorted_tasks()

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

    async def _build_assigned_devices(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task: TaskDef,
    ) -> dict[str, DeviceAssignmentDef] | None:
        """Build the dict of assigned devices (dynamic + specific). Returns None if stale."""
        task_name = task.name
        assigned_devices: dict[str, DeviceAssignmentDef] = {}

        # Start with solver-assigned dynamic devices
        solver_assignments = self._device_assignments.get(experiment_name, {}).get(task_name, {})
        assigned_devices.update(solver_assignments)

        # Add specific devices from config (may override solver assignments if same name)
        for device_name, dev in task.devices.items():
            if isinstance(dev, DeviceAssignmentDef):
                assigned_devices[device_name] = dev

        # If the task had dynamic requirements but we don't have an assignment, schedule is stale
        has_dynamic = any(isinstance(d, DynamicDeviceAssignmentDef) for d in task.devices.values())
        if has_dynamic and not self._device_assignments.get(experiment_name, {}).get(task_name):
            self._schedule_is_stale = True
            return None

        return assigned_devices

    async def _build_resolved_resources(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task: TaskDef,
    ) -> dict[str, str] | None:
        """Resolve resources for a task based on solver output.

        Returns a mapping of resource_name -> resource_name, or None if assignments are missing (stale schedule).
        """
        task_name = task.name
        # If the task has any dynamic resources but no assignment, mark schedule stale
        has_dynamic = any(not isinstance(v, str) for v in task.resources.values())
        assigned = self._resource_assignments.get(experiment_name, {}).get(task_name)
        if has_dynamic and not assigned:
            self._schedule_is_stale = True
            return None

        # Merge: prefer solver assignments; fallback to explicit strings from config
        resolved: dict[str, str] = {}
        if assigned:
            resolved.update(assigned)
        for name, value in task.resources.items():
            if isinstance(value, str):
                resolved.setdefault(name, value)
        return resolved

    async def _check_resources_available(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task: TaskDef,
        assigned_devices: dict[str, DeviceAssignmentDef],
    ) -> bool:
        """Check if all required devices and resources are available. Returns False if unavailable."""
        if assigned_devices:
            checks = [self._check_device_available(db, task, experiment_name, dev) for dev in assigned_devices.values()]
            if not all(await asyncio.gather(*checks)):
                return False

        if task.resources:
            resource_checks = [
                self._check_resource_available(db, task, experiment_name, resource_name)
                for resource_name in task.resources.values()
            ]
            if not all(await asyncio.gather(*resource_checks)):
                return False

        return True
