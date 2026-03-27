"""Tests for device/resource hold behavior in greedy and CP-SAT schedulers.

The hold_test_protocol has three tasks:
  setup   -> uses D1 (shared, no hold) and D2 (hold=true)
  process -> uses D2 (ref to setup.held_device, hold=true)
  cleanup -> uses D1 (shared, no hold) and D2 (ref to setup.held_device, no hold)

When two protocol runs run concurrently, D2 should be held between tasks in the
same protocol run, preventing the other protocol run from stealing it.
D1 is shared and should be freely available between tasks.

The hold_test_dynamic_protocol mirrors the same structure but uses dynamic
device assignment (device_type: DT2) instead of a static assignment for D2.
"""

from eos.configuration.protocol_graph import ProtocolGraph
from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.entities.task import TaskSubmission
from tests.fixtures import *

HOLD_PROTOCOL = "hold_test_protocol"
HOLD_DYNAMIC_PROTOCOL = "hold_test_dynamic_protocol"


@pytest.fixture(params=["greedy", "cpsat"])
def scheduler(request, greedy_scheduler, cpsat_scheduler) -> AbstractScheduler:
    if request.param == "greedy":
        return greedy_scheduler
    return cpsat_scheduler


class _HoldTestBase:
    """Shared helpers for hold scheduling tests."""

    async def _init_scheduler(self, scheduler: AbstractScheduler) -> None:
        if hasattr(scheduler, "_schedule_is_stale"):
            await scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

    async def _create_protocol_run(self, db, protocol_run_manager, protocol: str, name: str):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=protocol, name=name, owner="test")
        )
        await protocol_run_manager.start_protocol_run(db, name)

    async def _complete_task(self, db, task_manager, task_name: str, protocol_run_name: str):
        await task_manager.create_task(
            db, TaskSubmission(name=task_name, type="Noop", protocol_run_name=protocol_run_name)
        )
        await task_manager.start_task(db, protocol_run_name, task_name)
        await task_manager.complete_task(db, protocol_run_name, task_name)

    async def _spin_cycle(self, db, scheduler: AbstractScheduler) -> dict[str, dict[str, ScheduledTask]]:
        """Run one scheduling cycle for all registered protocol runs."""
        result: dict[str, dict[str, ScheduledTask]] = {}
        for name in list(scheduler._registered_protocol_runs.keys()):
            tasks = await scheduler.request_tasks(db, name)
            result[name] = {t.name: t for t in tasks}
        return result

    async def _spin_and_complete_all(
        self,
        db,
        scheduler: AbstractScheduler,
        task_manager,
        max_cycles: int = 30,
    ) -> list[tuple[str, str]]:
        """Spin cycles, completing every scheduled task immediately."""
        completed_order: list[tuple[str, str]] = []
        completed_set: set[tuple[str, str]] = set()

        for _ in range(max_cycles):
            all_tasks = await self._spin_cycle(db, scheduler)

            newly_scheduled = []
            for run_name, tasks in all_tasks.items():
                for task_name, _task in tasks.items():
                    if (run_name, task_name) not in completed_set:
                        newly_scheduled.append((run_name, task_name))

            if not newly_scheduled:
                all_done = True
                for name in list(scheduler._registered_protocol_runs.keys()):
                    if not await scheduler.is_protocol_run_completed(db, name):
                        all_done = False
                        break
                if all_done:
                    break
                continue

            for run_name, task_name in newly_scheduled:
                await self._complete_task(db, task_manager, task_name, run_name)
                completed_set.add((run_name, task_name))
                completed_order.append((run_name, task_name))

        return completed_order


@pytest.mark.parametrize("setup_lab_protocol", [("abstract_lab", HOLD_PROTOCOL)], indirect=True)
class TestSchedulerHold(_HoldTestBase):
    @pytest.mark.asyncio
    async def test_hold_prevents_device_stealing(
        self, db, scheduler, configuration_manager, protocol_run_manager, task_manager, allocation_manager
    ):
        """D2 is never used by two protocol runs simultaneously due to hold."""
        await self._init_scheduler(scheduler)
        graph1 = ProtocolGraph(configuration_manager.protocols[HOLD_PROTOCOL])
        graph2 = ProtocolGraph(configuration_manager.protocols[HOLD_PROTOCOL])

        await self._create_protocol_run(db, protocol_run_manager, HOLD_PROTOCOL, "run1")
        await self._create_protocol_run(db, protocol_run_manager, HOLD_PROTOCOL, "run2")
        await scheduler.register_protocol_run("run1", HOLD_PROTOCOL, graph1)
        await scheduler.register_protocol_run("run2", HOLD_PROTOCOL, graph2)

        completed_order = await self._spin_and_complete_all(db, scheduler, task_manager)

        run1_tasks = [t for e, t in completed_order if e == "run1"]
        run2_tasks = [t for e, t in completed_order if e == "run2"]
        assert set(run1_tasks) == {"setup", "process", "cleanup"}
        assert set(run2_tasks) == {"setup", "process", "cleanup"}

        # The hold chain on D2 means one protocol run must complete before the other starts
        run1_indices = [i for i, (e, _) in enumerate(completed_order) if e == "run1"]
        run2_indices = [i for i, (e, _) in enumerate(completed_order) if e == "run2"]

        assert max(run1_indices) < min(run2_indices) or max(run2_indices) < min(run1_indices), (
            f"D2 tasks interleaved between protocol runs! Order: {completed_order}"
        )

    @pytest.mark.asyncio
    async def test_no_hold_device_released(
        self, db, scheduler, configuration_manager, protocol_run_manager, task_manager, allocation_manager
    ):
        """D1 (no hold) is released after setup. D2 (hold=true) is held."""
        await self._init_scheduler(scheduler)
        graph = ProtocolGraph(configuration_manager.protocols[HOLD_PROTOCOL])

        await self._create_protocol_run(db, protocol_run_manager, HOLD_PROTOCOL, "run1")
        await scheduler.register_protocol_run("run1", HOLD_PROTOCOL, graph)

        for _ in range(10):
            all_tasks = await self._spin_cycle(db, scheduler)
            if "setup" in all_tasks.get("run1", {}):
                await self._complete_task(db, task_manager, "setup", "run1")
                break

        await self._spin_cycle(db, scheduler)

        d1_owner = scheduler._device_index.get(("abstract_lab", "D1"))
        d2_owner = scheduler._device_index.get(("abstract_lab", "D2"))

        assert d1_owner is None, f"D1 should be released (no hold), but owned by {d1_owner}"
        assert d2_owner is not None, "D2 should be held"
        assert d2_owner.protocol_run_name == "run1", "D2 should be held by run1"

    @pytest.mark.asyncio
    async def test_hold_cleanup_on_unregister(
        self, db, scheduler, configuration_manager, protocol_run_manager, task_manager, allocation_manager
    ):
        """Held locks are cleaned up when protocol run is unregistered."""
        await self._init_scheduler(scheduler)
        graph = ProtocolGraph(configuration_manager.protocols[HOLD_PROTOCOL])

        await self._create_protocol_run(db, protocol_run_manager, HOLD_PROTOCOL, "run1")
        await scheduler.register_protocol_run("run1", HOLD_PROTOCOL, graph)

        for _ in range(10):
            all_tasks = await self._spin_cycle(db, scheduler)
            if "setup" in all_tasks.get("run1", {}):
                await self._complete_task(db, task_manager, "setup", "run1")
                break

        await self._spin_cycle(db, scheduler)

        assert scheduler._device_index.get(("abstract_lab", "D2")) is not None

        await scheduler.unregister_protocol_run(db, "run1")

        assert scheduler._device_index.get(("abstract_lab", "D2")) is None

    @pytest.mark.asyncio
    async def test_hold_on_terminal_task_released(
        self, db, scheduler, configuration_manager, protocol_run_manager, task_manager, allocation_manager
    ):
        """Hold on the last task in the DAG is released immediately (no successors)."""
        await self._init_scheduler(scheduler)
        graph = ProtocolGraph(configuration_manager.protocols[HOLD_PROTOCOL])

        await self._create_protocol_run(db, protocol_run_manager, HOLD_PROTOCOL, "run1")
        await scheduler.register_protocol_run("run1", HOLD_PROTOCOL, graph)

        # Manually set hold on the cleanup task (terminal node)
        cleanup_task = graph.get_task("cleanup")
        cleanup_task.device_holds["held_device"] = True

        # Run all tasks to completion
        completed_order = await self._spin_and_complete_all(db, scheduler, task_manager)

        assert {t for _, t in completed_order} == {"setup", "process", "cleanup"}

        # D2 should NOT be held after cleanup (no successors)
        d2_owner = scheduler._device_index.get(("abstract_lab", "D2"))
        assert d2_owner is None, f"D2 should be released after terminal task, but owned by {d2_owner}"


@pytest.mark.parametrize("setup_lab_protocol", [("abstract_lab", HOLD_DYNAMIC_PROTOCOL)], indirect=True)
class TestSchedulerDynamicHold(_HoldTestBase):
    @pytest.mark.asyncio
    async def test_dynamic_hold_prevents_device_stealing(
        self, db, scheduler, configuration_manager, protocol_run_manager, task_manager, allocation_manager
    ):
        """Dynamically assigned D2 is never used by two protocol runs simultaneously due to hold."""
        await self._init_scheduler(scheduler)
        graph1 = ProtocolGraph(configuration_manager.protocols[HOLD_DYNAMIC_PROTOCOL])
        graph2 = ProtocolGraph(configuration_manager.protocols[HOLD_DYNAMIC_PROTOCOL])

        await self._create_protocol_run(db, protocol_run_manager, HOLD_DYNAMIC_PROTOCOL, "run1")
        await self._create_protocol_run(db, protocol_run_manager, HOLD_DYNAMIC_PROTOCOL, "run2")
        await scheduler.register_protocol_run("run1", HOLD_DYNAMIC_PROTOCOL, graph1)
        await scheduler.register_protocol_run("run2", HOLD_DYNAMIC_PROTOCOL, graph2)

        completed_order = await self._spin_and_complete_all(db, scheduler, task_manager)

        run1_tasks = [t for e, t in completed_order if e == "run1"]
        run2_tasks = [t for e, t in completed_order if e == "run2"]
        assert set(run1_tasks) == {"setup", "process", "cleanup"}
        assert set(run2_tasks) == {"setup", "process", "cleanup"}

        run1_indices = [i for i, (e, _) in enumerate(completed_order) if e == "run1"]
        run2_indices = [i for i, (e, _) in enumerate(completed_order) if e == "run2"]

        assert max(run1_indices) < min(run2_indices) or max(run2_indices) < min(run1_indices), (
            f"D2 tasks interleaved between protocol runs! Order: {completed_order}"
        )

    @pytest.mark.asyncio
    async def test_dynamic_hold_device_released_vs_held(
        self, db, scheduler, configuration_manager, protocol_run_manager, task_manager, allocation_manager
    ):
        """D1 (static, no hold) is released after setup. D2 (dynamic, hold=true) is held."""
        await self._init_scheduler(scheduler)
        graph = ProtocolGraph(configuration_manager.protocols[HOLD_DYNAMIC_PROTOCOL])

        await self._create_protocol_run(db, protocol_run_manager, HOLD_DYNAMIC_PROTOCOL, "run1")
        await scheduler.register_protocol_run("run1", HOLD_DYNAMIC_PROTOCOL, graph)

        for _ in range(10):
            all_tasks = await self._spin_cycle(db, scheduler)
            if "setup" in all_tasks.get("run1", {}):
                await self._complete_task(db, task_manager, "setup", "run1")
                break

        await self._spin_cycle(db, scheduler)

        d1_owner = scheduler._device_index.get(("abstract_lab", "D1"))
        d2_owner = scheduler._device_index.get(("abstract_lab", "D2"))

        assert d1_owner is None, f"D1 should be released (no hold), but owned by {d1_owner}"
        assert d2_owner is not None, "D2 should be held (dynamic assignment with hold=true)"
        assert d2_owner.protocol_run_name == "run1", "D2 should be held by run1"
