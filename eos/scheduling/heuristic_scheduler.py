import asyncio
import math
import time
from functools import partial

from eos.allocation.allocation_manager import AllocationManager
from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import DeviceAssignmentDef, TaskDef
from eos.configuration.protocol_graph import ProtocolGraph
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.devices.device_manager import DeviceManager
from eos.logging.logger import log
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.scheduling.abstract_scheduler import SCHEDULER_POLL_INTERVAL
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.scheduling.greedy_scheduler import GreedyScheduler
from eos.scheduling.simulation import PLAN_TIME_BUDGET_S, bottom_levels, plan_priorities
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject


class HeuristicScheduler(GreedyScheduler):
    """
    Greedy dispatch in an order planned by rollout search.

    When runs register or unregister, the remaining work of all runs is simulated under several job shop dispatch
    rules and randomized variants, and the best order is kept. Tasks still start as soon as they are ready and
    their devices/resources are free, but contended devices go to the tasks the plan ranks first.
    """

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
        self._priorities: dict[tuple[str, str], int] = {}
        self._run_priorities: dict[str, int] = {}
        self._plan_is_stale = True
        self._time_budget_s = PLAN_TIME_BUDGET_S
        self._dispatched_at: dict[tuple[str, str], float] = {}
        self._ready: dict[str, list[ScheduledTask]] = {}
        self._dispatch_errors: dict[str, Exception] = {}
        self._pending_plan: asyncio.Future | None = None
        self._dispatched_version: int | None = None
        self._dispatched_completed: dict[str, set[str]] = {}
        self._bottom_levels: dict[str, dict[str, int]] = {}
        self._dispatched_time = 0.0
        log.debug("Heuristic scheduler initialized.")

    async def register_protocol_run(self, protocol_run_name: str, protocol: str, protocol_graph: ProtocolGraph) -> None:
        async with self._lock:
            await super().register_protocol_run(protocol_run_name, protocol, protocol_graph)
            self._bottom_levels[protocol_run_name] = bottom_levels(protocol_graph, self._task_defs[protocol_run_name])
            self._plan_is_stale = True

    async def unregister_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        async with self._lock:
            await super().unregister_protocol_run(db, protocol_run_name)
            self._bottom_levels.pop(protocol_run_name, None)
            self._ready.pop(protocol_run_name, None)
            self._dispatch_errors.pop(protocol_run_name, None)
            self._dispatched_at = {k: v for k, v in self._dispatched_at.items() if k[0] != protocol_run_name}
            self._plan_is_stale = True

    async def update_parameters(self, parameters: dict) -> None:
        async with self._lock:
            self._state_version += 1
            self._time_budget_s = float(parameters.get("time_budget_s", self._time_budget_s))

    async def release_task(self, db: AsyncDbSession, task_name: str, protocol_run_name: str | None = None) -> None:
        async with self._lock:
            self._dispatched_at.pop((protocol_run_name, task_name), None)
            await super().release_task(db, task_name, protocol_run_name)

    async def request_tasks(self, db: AsyncDbSession, protocol_run_name: str) -> list[ScheduledTask]:
        async with self._lock:
            if protocol_run_name not in self._registered_protocol_runs:
                raise EosSchedulerRegistrationError(
                    f"Cannot request tasks from the scheduler for unregistered protocol run {protocol_run_name}."
                )

            # One dispatch serves every run until the scheduling state or the plan change. Completions and skips
            # change the state version, so serving the cached dispatch needs no database read.
            plan_finished = self._pending_plan is not None and self._pending_plan.done()
            if (
                not plan_finished
                and self._dispatched_version == self._state_version
                and time.monotonic() - self._dispatched_time < SCHEDULER_POLL_INTERVAL
            ):
                return await self._take_ready(db, protocol_run_name, self._dispatched_completed.get(protocol_run_name))

            run_names = list(self._registered_protocol_runs)
            await self._restore_assignments(db, run_names)
            all_completed = await self._protocol_run_manager.get_all_completed_and_skipped_tasks(db, run_names)
            completed_by_run = {run_name: all_completed.get(run_name, set()) for run_name in run_names}

            self._clear_per_cycle_caches()

            try:
                await self._release_completed_allocations(db, completed_by_run)
                self._dispatched_at = {
                    key: t for key, t in self._dispatched_at.items() if key[1] not in completed_by_run.get(key[0], ())
                }
                if self._pending_plan is not None and self._pending_plan.done():
                    self._apply_plan()
                if self._plan_is_stale and self._pending_plan is None:
                    await self._start_plan(db, completed_by_run)
                await self._dispatch(db, completed_by_run)
                self._dispatched_version = self._state_version
                self._dispatched_completed = completed_by_run
                self._dispatched_time = time.monotonic()
                return await self._take_ready(db, protocol_run_name, completed_by_run[protocol_run_name])
            finally:
                self._clear_per_cycle_caches()

    async def _take_ready(
        self, db: AsyncDbSession, protocol_run_name: str, settled: set[str] | None
    ) -> list[ScheduledTask]:
        """Hand a run its buffered tasks, dropping any it settled (e.g. skipped) after they were dispatched."""
        if error := self._dispatch_errors.pop(protocol_run_name, None):
            raise error
        ready = self._ready.pop(protocol_run_name, [])
        settled = settled or set()
        for scheduled_task in ready:
            if scheduled_task.name in settled:
                self._dispatched_at.pop((protocol_run_name, scheduled_task.name), None)
                self._dispatched_tasks.get(protocol_run_name, set()).discard(scheduled_task.name)
                # Hold aware, since the task may have taken over an item held for later tasks
                await self._release_protocol_run_task(db, scheduled_task.name, protocol_run_name, settled)
        ready = [scheduled_task for scheduled_task in ready if scheduled_task.name not in settled]
        self._check_deadlock(protocol_run_name, bool(ready))
        return ready

    async def _dispatch(self, db: AsyncDbSession, completed_by_run: dict[str, set[str]]) -> None:
        """Allocate ready tasks of all runs in planned order, buffering each run's tasks until it requests them."""
        # Tasks the plan has not ranked yet, e.g. of a run that just registered, go by most work remaining
        candidates = sorted(
            (
                (
                    -self._run_priorities.get(run_name, 0),
                    self._priorities.get((run_name, task_name), math.inf),
                    -self._bottom_levels[run_name][task_name],
                ),
                run_name,
                task_name,
            )
            for run_name, completed in completed_by_run.items()
            for task_name in self._schedulable_tasks(run_name, completed)
        )

        for _, run_name, task_name in candidates:
            _, protocol_graph = self._registered_protocol_runs[run_name]
            completed = completed_by_run[run_name]
            try:
                scheduled_task = await self._check_and_allocate_resources(
                    db, run_name, task_name, completed, protocol_graph
                )
            except Exception as e:
                # Raised when the owning run requests, not in whichever run triggered this dispatch
                self._dispatch_errors.setdefault(run_name, e)
                self._state_version += 1  # Wake the owning run so it fails promptly
                continue
            if scheduled_task:
                self._ready.setdefault(run_name, []).append(scheduled_task)

    async def _finalize_scheduling(
        self,
        db: AsyncDbSession,
        protocol_run_name: str,
        task_name: str,
        task: TaskDef,
        assigned_devices: dict[str, DeviceAssignmentDef],
    ) -> ScheduledTask | None:
        scheduled = await super()._finalize_scheduling(db, protocol_run_name, task_name, task, assigned_devices)
        if scheduled:
            self._dispatched_at[(protocol_run_name, task_name)] = time.monotonic()
        return scheduled

    async def _start_plan(self, db: AsyncDbSession, completed_by_run: dict[str, set[str]]) -> None:
        """Plan dispatch priorities from a snapshot in a worker thread. Dispatch keeps the old plan meanwhile."""
        self._plan_is_stale = False
        run_names = list(self._registered_protocol_runs)
        self._run_priorities = await self._get_protocol_run_priorities(db, run_names)

        now = time.monotonic()

        def remaining_time(run_name: str, task_name: str, duration: int) -> int:
            return round(duration - (now - self._dispatched_at.get((run_name, task_name), now)))

        labs, instances, running, locks = self._planning_snapshot(
            completed_by_run, self._run_priorities, remaining_time
        )
        self._pending_plan = asyncio.get_running_loop().run_in_executor(
            None, partial(plan_priorities, labs, instances, running, locks, self._time_budget_s)
        )
        self._pending_plan.add_done_callback(self._on_plan_done)

    def _on_plan_done(self, _future: asyncio.Future) -> None:
        self._state_version += 1  # Re-dispatch with the new plan

    def _apply_plan(self) -> None:
        future, self._pending_plan = self._pending_plan, None
        try:
            plan = future.result()
        except Exception as e:
            log.error(f"Dispatch planning failed, keeping the previous plan: {e}")
            return
        registered = self._registered_protocol_runs
        self._priorities = {key: rank for key, rank in plan.priorities.items() if key[0] in registered}
        self._state_version += 1  # Other runs re-request under the new plan
        log.info(f"Planned dispatch order (expected makespan={plan.makespan}, rollouts={plan.rollouts}).")
