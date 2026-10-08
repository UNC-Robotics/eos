import asyncio
import time
from functools import partial

from ortools.sat.sat_parameters_pb2 import SatParameters

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import DynamicDeviceAssignmentDef, TaskDef, DeviceAssignmentDef
from eos.configuration.protocol_graph import ProtocolGraph
from eos.configuration.utils import is_device_reference, is_resource_reference
from eos.devices.device_manager import DeviceManager
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.allocation.allocation_manager import AllocationManager
from eos.scheduling.abstract_scheduler import SCHEDULER_POLL_INTERVAL
from eos.scheduling.base_scheduler import AllocationEntry, BaseScheduler
from eos.scheduling.cpsat_scheduling_solver import (
    DEVICE,
    RESOURCE,
    CpSatSchedulingSolver,
    HeldAllocation,
    SchedulingSolution,
)
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerError, EosSchedulerRegistrationError
from eos.scheduling.simulation import PLAN_TIME_BUDGET_S, plan_priorities
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject


SOLVE_RETRY_INTERVAL = 10.0  # seconds between attempts after a failed solve


def _plan_and_solve(solver: CpSatSchedulingSolver, plan_inputs: tuple, plan_budget_s: float) -> SchedulingSolution:
    """Warm-start CP-SAT with the heuristic planner's schedule, which is also used if CP-SAT finds none in time."""
    hint = None
    if plan_budget_s > 0:
        hint = plan_priorities(*plan_inputs, time_budget_s=plan_budget_s, stop=solver.stopped).schedule
    return solver.solve(hint=hint)


def _with_actual(planned: dict[str, dict[str, dict]], actual: dict[str, dict[str, dict]]) -> dict[str, dict[str, dict]]:
    """Planned assignments, overridden by those dispatched tasks actually got."""
    merged = {run: dict(tasks) for run, tasks in planned.items()}
    for run, tasks in actual.items():
        merged.setdefault(run, {}).update(tasks)
    return merged


class CpSatScheduler(BaseScheduler):
    """Global scheduler using CP-SAT with makespan then start-time minimization."""

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        protocol_run_manager: ProtocolRunManager,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        allocation_manager: AllocationManager,
    ):
        super().__init__(configuration_manager, protocol_run_manager, task_manager, device_manager, allocation_manager)
        self._schedule: dict[str, dict[str, int]] = {}
        self._schedule_is_stale = False
        self._task_durations: dict[str, dict[str, int]] = {}
        self._current_time: int = 0
        self._device_assignments: dict[str, dict[str, dict[str, DeviceAssignmentDef]]] = {}
        self._resource_assignments: dict[str, dict[str, dict[str, str]]] = {}
        self._parameter_overrides: dict[str, float | int | bool] = {}
        self._pending_solve: (
            tuple[asyncio.Future[SchedulingSolution], dict[str, dict[str, int]], CpSatSchedulingSolver] | None
        ) = None
        self._solve_retry_at: float | None = None
        self._warm_start_budget_s = PLAN_TIME_BUDGET_S
        self._completed: dict[str, set[str]] = {}
        self._completed_version = -1
        self._planned_active_devices: set[tuple[str, str]] | None = None
        self._devices_checked_at = 0.0

        log.debug("CP-SAT scheduler initialized.")

    async def register_protocol_run(self, protocol_run_name: str, protocol: str, protocol_graph: ProtocolGraph) -> None:
        async with self._lock:
            await super().register_protocol_run(protocol_run_name, protocol, protocol_graph)
            self._schedule_is_stale = True

    async def unregister_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        async with self._lock:
            unfinished = set(self._schedule.get(protocol_run_name, {})) - self._settled_tasks.get(
                protocol_run_name, set()
            )
            await super().unregister_protocol_run(db, protocol_run_name)
            self._schedule.pop(protocol_run_name, None)
            self._device_assignments.pop(protocol_run_name, None)
            self._resource_assignments.pop(protocol_run_name, None)
            self._task_durations.pop(protocol_run_name, None)
            if not self._registered_protocol_runs:
                self._current_time = 0
                self._discard_pending_solve()
            elif unfinished:
                # Remaining runs may have been planned behind its unfinished work
                self._schedule_is_stale = True

    def _restore_task_assignments(
        self, protocol_run_name: str, task_name: str, devices: dict[str, DeviceAssignmentDef], resources: dict[str, str]
    ) -> None:
        super()._restore_task_assignments(protocol_run_name, task_name, devices, resources)
        self._device_assignments.setdefault(protocol_run_name, {}).setdefault(task_name, devices)
        self._resource_assignments.setdefault(protocol_run_name, {}).setdefault(task_name, resources)

    async def update_parameters(self, parameters: dict) -> None:
        await super().update_parameters(parameters)
        async with self._lock:
            parameters = dict(parameters)
            self._warm_start_budget_s = float(parameters.pop("warm_start_budget_s", self._warm_start_budget_s))
            for name, value in parameters.items():
                try:
                    setattr(SatParameters(), name, value)
                except (AttributeError, TypeError, ValueError) as e:
                    raise EosSchedulerError(f"Invalid CP-SAT parameter '{name}': {e}") from e
            self._parameter_overrides.update(parameters)
            self._schedule_is_stale = True

    async def _start_solve(self, db: AsyncDbSession, completed_or_skipped_by_run: dict[str, set[str]]) -> None:
        """Solve a snapshot of the current state in a worker thread, so the scheduler stays usable meanwhile."""
        running_by_run = {
            run_name: self._running_tasks(run_name, completed_or_skipped_by_run.get(run_name, set()))
            for run_name in self._registered_protocol_runs
        }

        protocol_run_names = list(self._registered_protocol_runs.keys())
        protocol_run_priorities = await self._get_protocol_run_priorities(db, protocol_run_names)
        eligible_devices_by_type = await self._active_devices_by_type(db)
        self._planned_active_devices = set(self._active_device_set_cache)
        eligible_resources_by_type = self._resources_by_type_with_labs()

        def remaining_time(run_name: str, task_name: str, duration: int) -> int:
            start = self._schedule.get(run_name, {}).get(task_name)
            planned_duration = self._task_durations.get(run_name, {}).get(task_name, duration)
            return duration if start is None else start + planned_duration - self._current_time

        plan_inputs = self._planning_snapshot(completed_or_skipped_by_run, protocol_run_priorities, remaining_time)

        task_durations: dict[str, dict[str, int]] = {}  # Filled by the solver
        solver = CpSatSchedulingSolver(
            protocol_runs=dict(self._registered_protocol_runs),
            task_durations=task_durations,
            schedule=dict(self._schedule),
            completed_or_skipped_by_run=completed_or_skipped_by_run,
            running_by_exp=running_by_run,
            current_time=self._current_time,
            protocol_run_priorities=protocol_run_priorities,
            eligible_devices_by_type=eligible_devices_by_type,
            eligible_resources_by_type=eligible_resources_by_type,
            previous_device_assignments=_with_actual(self._device_assignments, self._assigned_devices),
            previous_resource_assignments=_with_actual(self._resource_assignments, self._assigned_resources),
            parameter_overrides=dict(self._parameter_overrides) or None,
            held_allocations=[
                HeldAllocation(entry.protocol_run_name, kind, item, entry.hold_for)
                for kind, index in ((DEVICE, self._device_index), (RESOURCE, self._resource_index))
                for item, entry in index.items()
                if entry.held
            ],
        )

        future = asyncio.get_running_loop().run_in_executor(
            None, partial(_plan_and_solve, solver, plan_inputs, self._warm_start_budget_s)
        )
        future.add_done_callback(self._on_solve_done)
        self._pending_solve = (future, task_durations, solver)

    def _discard_pending_solve(self) -> None:
        """Stop a solve nobody needs anymore instead of letting it use CPU until its time limit."""
        if self._pending_solve is None:
            return
        future, _, solver = self._pending_solve
        self._pending_solve = None
        solver.stop()
        future.add_done_callback(lambda done: done.cancelled() or done.exception())

    def _on_solve_done(self, _future: asyncio.Future) -> None:
        self._state_version += 1  # Runs re-request to pick up the new schedule

    def _apply_solve(self) -> None:
        """Adopt a finished solve for the runs that are still registered."""
        future, task_durations, _ = self._pending_solve
        self._pending_solve = None
        try:
            solution = future.result()
        except Exception as e:
            # Keep the previous schedule. Failing the requesting run would not fix e.g. all devices being inactive
            self._solve_retry_at = time.monotonic() + SOLVE_RETRY_INTERVAL
            log.error(f"CP-SAT scheduling failed, keeping the previous schedule and retrying: {e}")
            return

        registered = self._registered_protocol_runs
        planned_devices = {run: tasks for run, tasks in solution.device_assignments.items() if run in registered}
        planned_resources = {run: tasks for run, tasks in solution.resource_assignments.items() if run in registered}
        if self._conflicts(planned_devices, self._assigned_devices) or self._conflicts(
            planned_resources, self._assigned_resources
        ):
            # A task dispatched while the solve ran got something else than planned, so plan again from now
            self._schedule_is_stale = True

        self._schedule = {run: tasks for run, tasks in solution.schedule.items() if run in registered}
        self._task_durations = {run: tasks for run, tasks in task_durations.items() if run in registered}
        # Tasks dispatched while the solve ran keep what they actually got, and references follow them
        self._device_assignments = _with_actual(planned_devices, self._assigned_devices)
        self._resource_assignments = _with_actual(planned_resources, self._assigned_resources)
        for run_name in self._schedule:
            self._follow_references(run_name)
        self._state_version += 1  # Other runs re-request against the new schedule

    async def request_tasks(self, db: AsyncDbSession, protocol_run_name: str) -> list[ScheduledTask]:
        async with self._lock:
            self._clear_per_cycle_caches()
            if protocol_run_name not in self._registered_protocol_runs:
                raise EosSchedulerRegistrationError(f"ProtocolRun {protocol_run_name} is not registered.")

            all_completed_by_run = await self._completed_by_run(db)
            completed_tasks = all_completed_by_run.get(protocol_run_name, set())
            try:
                if self._pending_solve is not None and self._pending_solve[0].done():
                    self._apply_solve()

                await self._release_completed_allocations(db, all_completed_by_run)
                self._advance_time(all_completed_by_run)

                await self._check_device_status(db)
                if self._solve_retry_at is not None and time.monotonic() >= self._solve_retry_at:
                    self._solve_retry_at = None
                    self._schedule_is_stale = True

                if self._schedule_is_stale and self._pending_solve is None:
                    self._schedule_is_stale = False
                    await self._restore_assignments(db, list(self._registered_protocol_runs))
                    await self._start_solve(db, all_completed_by_run)

                run_schedule = self._schedule.get(protocol_run_name)
                if run_schedule is None:
                    return []  # Not planned yet

                _, protocol_graph = self._registered_protocol_runs[protocol_run_name]
                next_in_plan = self._next_in_plan(all_completed_by_run)

                scheduled_tasks = []
                for task_name in self._schedulable_tasks(protocol_run_name, completed_tasks):
                    if (protocol_run_name, task_name) not in next_in_plan:
                        continue

                    scheduled_task = await self._check_and_allocate_resources(
                        db, protocol_run_name, task_name, completed_tasks, protocol_graph
                    )
                    if scheduled_task:
                        scheduled_tasks.append(scheduled_task)

                self._check_deadlock(protocol_run_name, bool(scheduled_tasks))
                return scheduled_tasks
            finally:
                if self._schedule_is_stale and self._pending_solve is None:
                    self._state_version += 1  # The next request starts a solve. A running one wakes runs when done.
                self._clear_per_cycle_caches()

    async def _check_device_status(self, db: AsyncDbSession) -> None:
        """Plan again when devices were activated or deactivated since the last solve, at most once per poll."""
        if time.monotonic() - self._devices_checked_at < SCHEDULER_POLL_INTERVAL:
            return
        self._devices_checked_at = time.monotonic()
        await self._active_devices_by_type(db)
        if self._planned_active_devices is not None and self._active_device_set_cache != self._planned_active_devices:
            self._schedule_is_stale = True

    async def _completed_by_run(self, db: AsyncDbSession) -> dict[str, set[str]]:
        """Completed and skipped tasks of all runs, read again only after the scheduling state changed."""
        if self._completed_version != self._state_version:
            self._completed = await self._protocol_run_manager.get_all_completed_and_skipped_tasks(
                db, list(self._registered_protocol_runs)
            )
            self._completed_version = self._state_version
        return self._completed

    @staticmethod
    def _conflicts(planned: dict[str, dict[str, dict]], actual: dict[str, dict[str, dict]]) -> bool:
        return any(
            planned.get(run, {}).get(task, assigned) != assigned
            for run, tasks in actual.items()
            for task, assigned in tasks.items()
        )

    def _follow_references(self, protocol_run_name: str) -> None:
        """Point planned references at what the referenced tasks are planned or dispatched to use."""
        devices = self._device_assignments.setdefault(protocol_run_name, {})
        resources = self._resource_assignments.setdefault(protocol_run_name, {})
        for task_name in self._topo_sorted_cache[protocol_run_name]:
            if task_name in self._assigned_devices.get(protocol_run_name, {}):
                continue  # Already dispatched with what it got
            task = self._task_defs[protocol_run_name][task_name]
            for slots, planned, is_reference in (
                (task.devices, devices, is_device_reference),
                (task.resources, resources, is_resource_reference),
            ):
                for slot, value in slots.items():
                    if isinstance(value, str) and is_reference(value):
                        ref_task, ref_slot = value.split(".")
                        if (target := planned.get(ref_task, {}).get(ref_slot)) is not None:
                            planned.setdefault(task_name, {})[slot] = target

    def _next_in_plan(self, completed_by_run: dict[str, set[str]]) -> set[tuple[str, str]]:
        """
        Planned tasks that are next in the planned order on all of their devices and resources.

        The plan is executed as an order rather than a timetable, so a task does not wait for the planned start
        time when everything it needs is already free, e.g. because a task took less time than planned.
        """
        held = {
            item: entry for item, entry in [*self._device_index.items(), *self._resource_index.items()] if entry.held
        }
        pending = []
        first_user: dict[object, tuple[int, str, int]] = {}
        for run_name, tasks in self._schedule.items():
            settled = completed_by_run.get(run_name, set()) | self._dispatched_tasks.get(run_name, set())
            topo_index = {name: i for i, name in enumerate(self._topo_sorted_cache.get(run_name, ()))}
            for task_name, start in tasks.items():
                if task_name in settled:
                    continue
                items = self._planned_items(run_name, task_name)
                # A task that cannot take an item held for others must not keep the hold users waiting
                blocking = [
                    held[item]
                    for item, named in items.items()
                    if item in held and not self._is_hold_transparent(held[item], task_name, run_name, named)
                ]
                if blocking:
                    self._replan_if_before_hold_users(run_name, task_name, start, blocking)
                    continue
                # Ties go to the earlier task in the run, e.g. a zero duration task before its successor
                order = (start, run_name, topo_index.get(task_name, 0))
                pending.append((order, task_name, items))
                for item in items:
                    first_user[item] = min(first_user.get(item, order), order)
        return {
            (order[1], task_name)
            for order, task_name, items in pending
            if all(first_user[item] == order for item in items)
        }

    def _planned_items(self, run_name: str, task_name: str) -> dict[object, bool]:
        """The devices and resources a task is planned to use, and whether it names each of them."""
        named_devices, named_resources = self._named_slots(run_name, task_name)
        devices = self._device_assignments.get(run_name, {}).get(task_name, {})
        resources = self._resource_assignments.get(run_name, {}).get(task_name, {})
        return {(d.lab_name, d.name): slot in named_devices for slot, d in devices.items()} | {
            name: slot in named_resources for slot, name in resources.items()
        }

    def _replan_if_before_hold_users(
        self, run_name: str, task_name: str, start: int, blocking: list[AllocationEntry]
    ) -> None:
        """A plan that puts a task before the hold users of an item it cannot take is wrong, so plan again."""
        for entry in blocking:
            user_starts = [self._schedule.get(entry.protocol_run_name, {}).get(user) for user in entry.hold_for]
            if any(user_start is not None and user_start > start for user_start in user_starts):
                log.debug(f"RUN '{run_name}' - '{task_name}' was planned during a hold, replanning")
                self._schedule_is_stale = True
                return

    def _advance_time(self, completed_by_run: dict[str, set[str]]) -> None:
        """Move the schedule clock to the latest planned end of a settled task."""
        for run, completed in completed_by_run.items():
            starts = self._schedule.get(run, {})
            durations = self._task_durations.get(run, {})
            for task_name in completed:
                if task_name in starts and task_name in durations:
                    self._current_time = max(self._current_time, starts[task_name] + durations[task_name])

        # Jump to the next planned start when nothing runs, so a gap in a time-limited plan cannot stall
        if any(self._running_tasks(run, completed_by_run.get(run, set())) for run in self._schedule):
            return
        next_starts = [
            start
            for run, tasks in self._schedule.items()
            for task_name, start in tasks.items()
            if task_name not in completed_by_run.get(run, set())
        ]
        if next_starts:
            self._current_time = max(self._current_time, min(next_starts))

    async def _build_assigned_devices(
        self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef
    ) -> dict[str, DeviceAssignmentDef] | None:
        task_name = task.name
        assigned_devices: dict[str, DeviceAssignmentDef] = {}

        solver_assignments = self._device_assignments.get(protocol_run_name, {}).get(task_name, {})
        assigned_devices.update(solver_assignments)

        for device_name, dev in task.devices.items():
            if isinstance(dev, DeviceAssignmentDef):
                assigned_devices[device_name] = dev
            # The referenced task may have run on another device than a later solve planned
            elif (
                isinstance(dev, str)
                and is_device_reference(dev)
                and (actual := self._referenced_device(protocol_run_name, dev)) is not None
            ):
                assigned_devices[device_name] = actual

        has_dynamic = any(isinstance(d, DynamicDeviceAssignmentDef) for d in task.devices.values())
        if has_dynamic and not self._device_assignments.get(protocol_run_name, {}).get(task_name):
            self._schedule_is_stale = True
            return None

        # A planned device that was removed or deactivated after the solve needs a new plan
        await self._active_devices_by_type(db)
        if any((dev.lab_name, dev.name) not in self._active_device_set_cache for dev in solver_assignments.values()):
            self._schedule_is_stale = True
            return None

        return assigned_devices

    async def _build_resolved_resources(
        self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef
    ) -> dict[str, str] | None:
        task_name = task.name
        has_dynamic = any(not isinstance(v, str) for v in task.resources.values())
        assigned = self._resource_assignments.get(protocol_run_name, {}).get(task_name)
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

        # Named and resolved reference resources are what the referenced tasks actually got, so they win
        return {**(assigned or {}), **{name: value for name, value in task.resources.items() if isinstance(value, str)}}
