import asyncio
import time

from ortools.sat.python import cp_model
from sqlalchemy import select

from eos.allocation.entities.device_allocation import DeviceAllocationModel
from eos.configuration.entities.protocol_def import ProtocolDef
from eos.configuration.entities.task_def import DeviceAssignmentDef, DynamicDeviceAssignmentDef, TaskDef
from eos.configuration.protocol_graph import ProtocolGraph
from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.scheduling import heuristic_scheduler as heuristic_scheduler_module
from eos.scheduling.base_scheduler import AllocationEntry
from eos.scheduling.cpsat_scheduling_solver import CpSatSchedulingSolver
from eos.scheduling.exceptions import EosSchedulerError
from eos.scheduling.entities.planned_task import PlannedTask
from eos.tasks.entities.task import TaskSubmission
from tests.fixtures import *

LAB = "multiplication_lab"
PROTOCOL = "run_if"
MULTIPLIER = (LAB, "multiplier")


async def _register(db, scheduler, protocol_run_manager, configuration_manager, name: str) -> None:
    await protocol_run_manager.create_protocol_run(
        db, ProtocolRunSubmission(name=name, type=PROTOCOL, owner="test", parameters={"prep": {"number": 5}})
    )
    await protocol_run_manager.start_protocol_run(db, name)
    await scheduler.register_protocol_run(name, PROTOCOL, ProtocolGraph(configuration_manager.protocols[PROTOCOL]))


def _make(
    scheduler_class, configuration_manager, protocol_run_manager, task_manager, device_manager, allocation_manager
):
    scheduler = scheduler_class(
        configuration_manager, protocol_run_manager, task_manager, device_manager, allocation_manager
    )
    if isinstance(scheduler, HeuristicScheduler):
        scheduler._time_budget_s = TEST_PLAN_TIME_BUDGET_S
    return scheduler


@pytest.mark.parametrize("setup_lab_protocol", [(LAB, PROTOCOL)], indirect=True)
class TestSchedulerFixes:
    @pytest.fixture
    def make_scheduler(
        self, configuration_manager, protocol_run_manager, task_manager, device_manager, allocation_manager
    ):
        def make(scheduler_class):
            return _make(
                scheduler_class,
                configuration_manager,
                protocol_run_manager,
                task_manager,
                device_manager,
                allocation_manager,
            )

        return make

    @pytest.mark.parametrize("scheduler_class", [GreedyScheduler, CpSatScheduler])
    async def test_running_tasks_are_not_dispatched_again(
        self, db, make_scheduler, scheduler_class, protocol_run_manager, configuration_manager
    ):
        scheduler = make_scheduler(scheduler_class)
        await _register(db, scheduler, protocol_run_manager, configuration_manager, "run")

        assert [task.name for task in await request_tasks(scheduler, db, "run")] == ["prep"]
        version = scheduler.state_version
        assert await request_tasks(scheduler, db, "run") == []
        assert scheduler.state_version == version  # No re-allocation churn

    async def test_cpsat_replans_whenever_a_run_unregisters(
        self, db, make_scheduler, protocol_run_manager, configuration_manager
    ):
        scheduler = make_scheduler(CpSatScheduler)
        for name in ("first", "second"):
            await _register(db, scheduler, protocol_run_manager, configuration_manager, name)
        await request_tasks(scheduler, db, "first")
        assert not scheduler._schedule_is_stale

        await scheduler.unregister_protocol_run(db, "first")  # Even without running tasks
        assert scheduler._schedule_is_stale

    async def test_cpsat_keeps_the_schedule_when_a_solve_fails(
        self, db, make_scheduler, protocol_run_manager, configuration_manager, monkeypatch
    ):
        scheduler = make_scheduler(CpSatScheduler)
        await _register(db, scheduler, protocol_run_manager, configuration_manager, "run")
        await request_tasks(scheduler, db, "run")
        schedule = scheduler._schedule

        def fail(_solver):
            raise EosSchedulerError("infeasible")

        monkeypatch.setattr(CpSatSchedulingSolver, "solve", fail)
        scheduler._schedule_is_stale = True
        assert await request_tasks(scheduler, db, "run") == []  # Does not raise into the requesting run
        assert scheduler._schedule is schedule
        assert scheduler._solve_retry_at is not None

    async def test_cpsat_skips_idle_gaps_in_the_plan(
        self, db, make_scheduler, protocol_run_manager, configuration_manager
    ):
        scheduler = make_scheduler(CpSatScheduler)
        await _register(db, scheduler, protocol_run_manager, configuration_manager, "run")
        scheduler._schedule_is_stale = True
        await scheduler.request_tasks(db, "run")
        await scheduler._pending_solve[0]
        scheduler._apply_solve()
        # A gap before the plan starts that no completion would close
        scheduler._schedule["run"] = {task: start + 50 for task, start in scheduler._schedule["run"].items()}

        assert [task.name for task in await scheduler.request_tasks(db, "run")] == ["prep"]
        assert scheduler._current_time == scheduler._schedule["run"]["prep"]

    async def test_heuristic_errors_fail_only_the_owning_run(
        self, db, make_scheduler, protocol_run_manager, configuration_manager, monkeypatch
    ):
        scheduler = make_scheduler(HeuristicScheduler)
        for name in ("healthy", "broken"):
            await _register(db, scheduler, protocol_run_manager, configuration_manager, name)
        check = scheduler._check_and_allocate_resources

        async def failing_check(db, run_name, *args):
            if run_name == "broken":
                raise ValueError("boom")
            return await check(db, run_name, *args)

        monkeypatch.setattr(scheduler, "_check_and_allocate_resources", failing_check)
        await request_tasks(scheduler, db, "healthy")
        with pytest.raises(ValueError, match="boom"):
            await request_tasks(scheduler, db, "broken")

    async def test_heuristic_planning_does_not_block_the_scheduler(
        self, db, make_scheduler, protocol_run_manager, configuration_manager, monkeypatch
    ):
        scheduler = make_scheduler(HeuristicScheduler)
        plan = heuristic_scheduler_module.plan_priorities

        def slow_plan(*args):
            time.sleep(1)
            return plan(*args)

        monkeypatch.setattr(heuristic_scheduler_module, "plan_priorities", slow_plan)
        await _register(db, scheduler, protocol_run_manager, configuration_manager, "run")

        start = time.monotonic()
        await scheduler.request_tasks(db, "run")
        await scheduler.release_task(db, "prep", "run")
        assert time.monotonic() - start < 0.5

        await scheduler._pending_plan
        await scheduler.request_tasks(db, "run")
        assert scheduler._pending_plan is None
        assert scheduler._priorities

    async def test_heuristic_applies_a_plan_that_finished_during_a_request(
        self, db, make_scheduler, protocol_run_manager, configuration_manager
    ):
        scheduler = make_scheduler(HeuristicScheduler)
        await _register(db, scheduler, protocol_run_manager, configuration_manager, "run")
        await scheduler.request_tasks(db, "run")
        await scheduler._pending_plan
        scheduler._dispatched_version = scheduler.state_version  # The done notification landed mid-dispatch

        version = scheduler.state_version
        await scheduler.request_tasks(db, "run")
        assert scheduler._pending_plan is None
        assert scheduler.state_version > version  # Other runs are woken to use the new plan

    async def test_hold_carries_over_and_is_only_available_to_hold_users(self, make_scheduler):
        scheduler = make_scheduler(GreedyScheduler)
        # a -> b -> c, and a -> d on another branch. a holds the device for c.
        entry = AllocationEntry(owner="a", protocol_run_name="run", hold_for=frozenset({"c"}), held=True)
        scheduler._device_index[MULTIPLIER] = entry

        assert scheduler._is_device_available(*MULTIPLIER, "c", "run")  # The hold user
        assert not scheduler._is_device_available(*MULTIPLIER, "b", "run")  # Runs before c, but wants another item
        assert not scheduler._is_device_available(*MULTIPLIER, "d", "run")  # Unrelated branch
        assert not scheduler._is_device_available(*MULTIPLIER, "c", "other_run")
        assert scheduler._inherited_hold(entry, "c", "run") == frozenset()

    async def test_cpsat_references_use_the_device_the_referenced_task_actually_got(self, db, make_scheduler):
        scheduler = make_scheduler(CpSatScheduler)
        actual = DeviceAssignmentDef(lab_name=LAB, name="multiplier")
        scheduler._assigned_devices["run"] = {"first": {"multiplier": actual}}
        # A solve that ran while "first" was dispatched planned another device for it
        planned = DeviceAssignmentDef(lab_name=LAB, name="analyzer")
        scheduler._device_assignments["run"] = {"second": {"multiplier": planned}}
        second = TaskDef(name="second", type="Multiplication", devices={"multiplier": "first.multiplier"})

        assert await scheduler._build_assigned_devices(db, "run", second) == {"multiplier": actual}

    async def test_cpsat_plan_order_is_not_blocked_by_tasks_waiting_for_held_items(self, make_scheduler):
        scheduler = make_scheduler(CpSatScheduler)
        d1, d2 = DeviceAssignmentDef(lab_name=LAB, name="d1"), DeviceAssignmentDef(lab_name=LAB, name="d2")
        # Run x holds d2 for its "use". Run y's "setup" is planned first on d1 and d2, but cannot get d2.
        scheduler._device_index[(LAB, "d2")] = AllocationEntry(
            owner="hold", protocol_run_name="x", hold_for=frozenset({"use"}), held=True
        )
        scheduler._schedule = {"x": {"use": 20, "cleanup": 21}, "y": {"setup": 16, "later": 30}}
        scheduler._device_assignments = {
            "x": {"use": {"d": d2}, "cleanup": {"d": d1}},
            "y": {"setup": {"a": d1, "b": d2}, "later": {"a": d1}},
        }

        assert scheduler._next_in_plan({}) == {("x", "use"), ("x", "cleanup")}

    async def test_resumed_runs_restore_device_assignments_of_completed_tasks(
        self, db, make_scheduler, protocol_run_manager, configuration_manager, task_manager
    ):
        scheduler = make_scheduler(GreedyScheduler)
        await _register(db, scheduler, protocol_run_manager, configuration_manager, "resumed")
        device = DeviceAssignmentDef(lab_name=LAB, name="multiplier")
        await task_manager.create_task(
            db,
            TaskSubmission(
                name="prep", type="Multiplication", protocol_run_name="resumed", devices={"multiplier": device}
            ),
        )
        await task_manager.start_task(db, "resumed", "prep")
        await task_manager.complete_task(db, "resumed", "prep")

        await scheduler.request_tasks(db, "resumed")
        assert scheduler._assigned_devices["resumed"]["prep"] == {"multiplier": device}

    async def test_devices_allocated_outside_the_scheduler_are_respected(
        self, db, make_scheduler, protocol_run_manager, configuration_manager, allocation_manager
    ):
        scheduler = make_scheduler(GreedyScheduler)
        await _register(db, scheduler, protocol_run_manager, configuration_manager, "run")
        await allocation_manager.allocate_devices(db, [MULTIPLIER], "scientist")

        assert await scheduler.request_tasks(db, "run") == []
        await allocation_manager.deallocate_devices(db, [MULTIPLIER])
        assert [task.name for task in await scheduler.request_tasks(db, "run")] == ["prep"]

    async def test_released_index_entries_free_their_db_allocations(self, db, make_scheduler, allocation_manager):
        scheduler = make_scheduler(GreedyScheduler)
        await allocation_manager.allocate_devices(db, [MULTIPLIER], "orphan")
        scheduler._device_index[MULTIPLIER] = AllocationEntry(owner="orphan", protocol_run_name="gone")

        await scheduler.release_task(db, "orphan", "gone")  # Run no longer registered
        assert MULTIPLIER not in scheduler._device_index
        assert not allocation_manager.is_device_allocated(*MULTIPLIER)
        rows = (await db.execute(select(DeviceAllocationModel))).scalars().all()
        assert rows == []

    async def test_on_demand_queue_priority_starvation_timeout_and_cancel(self, db, make_scheduler, allocation_manager):
        scheduler = make_scheduler(GreedyScheduler)
        device = {"multiplier": DeviceAssignmentDef(lab_name=LAB, name="multiplier")}
        await allocation_manager.allocate_devices(db, [MULTIPLIER], "scientist")

        def submission(name, priority=0, timeout=600):
            return TaskSubmission(
                name=name, type="Multiplication", devices=device, priority=priority, allocation_timeout=timeout
            )

        assert await scheduler.submit_on_demand_task(db, submission("low")) is None
        assert await scheduler.submit_on_demand_task(db, submission("high", priority=5)) is None
        assert await scheduler.submit_on_demand_task(db, submission("cancelled")) is None
        assert await scheduler.submit_on_demand_task(db, submission("expired", timeout=0)) is None
        await asyncio.sleep(0.01)

        assert await scheduler.cancel_on_demand_task("cancelled")
        assert not await scheduler.cancel_on_demand_task("cancelled")

        progress = await scheduler.process_pending_on_demand(db)
        assert progress.scheduled == []
        assert [task.name for task in progress.timed_out] == ["expired"]

        await allocation_manager.deallocate_devices(db, [MULTIPLIER])
        progress = await scheduler.process_pending_on_demand(db)
        assert [task.name for task, _ in progress.scheduled] == ["high"]  # Priority first, "low" waits

    async def test_deadlock_is_reported(self, make_scheduler):
        scheduler = make_scheduler(GreedyScheduler)
        for name in ("one", "two"):
            scheduler._registered_protocol_runs[name] = None
        scheduler._device_index[MULTIPLIER] = AllocationEntry(
            owner="a", protocol_run_name="one", hold_for=frozenset({"b"}), held=True
        )

        scheduler._check_deadlock("one", scheduled_any=False)
        assert scheduler._deadlock_reported_version == -1  # Not every run has been seen stuck yet
        scheduler._check_deadlock("two", scheduled_any=False)
        assert scheduler._deadlock_reported_version == scheduler.state_version

    async def test_lab_caches_follow_reloaded_labs(self, make_scheduler, configuration_manager):
        scheduler = make_scheduler(GreedyScheduler)
        first = scheduler._resources_by_type()
        lab = configuration_manager.labs[LAB]
        configuration_manager.labs[LAB] = lab.model_copy()
        try:
            assert scheduler._resources_by_type() is not first
        finally:
            configuration_manager.labs[LAB] = lab


class TestCpSatPinsRunningTasks:
    def test_running_task_keeps_its_dynamic_device(self):
        protocol = ProtocolDef(
            type="pin",
            desc="pin",
            labs=["dynamic_lab"],
            tasks=[
                TaskDef(
                    name="T", type="Noop", duration=10, devices={"d": DynamicDeviceAssignmentDef(device_type="DT3")}
                ),
                TaskDef(name="S", type="Noop", duration=10, dependencies=["T"], devices={"d": "T.d"}),
            ],
        )
        running_on = DeviceAssignmentDef(lab_name="dynamic_lab", name="DX3B")
        solver = CpSatSchedulingSolver(
            protocol_runs={"run": ("pin", ProtocolGraph(protocol))},
            task_durations={},
            schedule={"run": {"T": 0}},
            completed_or_skipped_by_run={"run": set()},
            running_by_exp={"run": {"T"}},
            current_time=0,
            protocol_run_priorities={"run": 0},
            eligible_devices_by_type={"DT3": [("dynamic_lab", "DX3A"), ("dynamic_lab", "DX3B")]},
            eligible_resources_by_type={},
            previous_device_assignments={"run": {"T": {"d": running_on}}},
        )

        solution = solver.solve()
        assert solution.device_assignments["run"]["T"]["d"] == running_on
        assert solution.device_assignments["run"]["S"]["d"] == running_on


class TestCpSatWarmStart:
    DX3A = DeviceAssignmentDef(lab_name="dynamic_lab", name="DX3A")
    DX3B = DeviceAssignmentDef(lab_name="dynamic_lab", name="DX3B")

    def _solver(self) -> CpSatSchedulingSolver:
        protocol = ProtocolDef(
            type="pair",
            desc="pair",
            labs=["dynamic_lab"],
            tasks=[
                TaskDef(
                    name=name, type="Noop", duration=10, devices={"d": DynamicDeviceAssignmentDef(device_type="DT3")}
                )
                for name in ("A", "B")
            ],
        )
        return CpSatSchedulingSolver(
            protocol_runs={"run": ("pair", ProtocolGraph(protocol))},
            task_durations={},
            schedule={},
            completed_or_skipped_by_run={"run": set()},
            running_by_exp={"run": set()},
            current_time=100,
            protocol_run_priorities={"run": 0},
            eligible_devices_by_type={"DT3": [("dynamic_lab", "DX3A"), ("dynamic_lab", "DX3B")]},
            eligible_resources_by_type={},
        )

    def _plan(self, *task_names: str) -> dict:
        devices = {"A": self.DX3A, "B": self.DX3B}
        return {("run", name): PlannedTask(0, {"d": devices[name]}, {}) for name in task_names}

    def test_the_planned_schedule_seeds_the_search(self):
        solver = self._solver()
        solution = solver.solve(hint=self._plan("A", "B"))
        assert solver.model.Proto().solution_hint.vars
        assert not solver.solver.parameters.optimize_with_lb_tree_search  # It would discard the hint
        assert solution.makespan == 110

    def test_the_planned_schedule_is_used_when_cp_sat_finds_none(self, monkeypatch):
        solver = self._solver()
        monkeypatch.setattr(solver.solver, "Solve", lambda model: cp_model.UNKNOWN)
        solution = solver.solve(hint=self._plan("A", "B"))
        assert solution.status == "planned"
        assert solution.schedule == {"run": {"A": 100, "B": 100}}
        assert solution.device_assignments["run"] == {"A": {"d": self.DX3A}, "B": {"d": self.DX3B}}

    def test_an_incomplete_plan_is_not_used(self, monkeypatch):
        solver = self._solver()
        monkeypatch.setattr(solver.solver, "Solve", lambda model: cp_model.UNKNOWN)
        with pytest.raises(EosSchedulerError):
            solver.solve(hint=self._plan("A"))
