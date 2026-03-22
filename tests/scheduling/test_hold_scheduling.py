"""Tests for device/resource hold behavior in greedy and CP-SAT schedulers.

The hold_test_experiment has three tasks:
  setup   -> uses D1 (shared, no hold) and D2 (hold=true)
  process -> uses D2 (ref to setup.held_device, hold=true)
  cleanup -> uses D1 (shared, no hold) and D2 (ref to setup.held_device, no hold)

When two experiments run concurrently, D2 should be held between tasks in the
same experiment, preventing the other experiment from stealing it.
D1 is shared and should be freely available between tasks.

The hold_test_dynamic_experiment mirrors the same structure but uses dynamic
device assignment (device_type: DT2) instead of a static assignment for D2.
"""

from eos.configuration.experiment_graph import ExperimentGraph
from eos.experiments.entities.experiment import ExperimentSubmission
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.entities.task import TaskSubmission
from tests.fixtures import *

HOLD_EXPERIMENT_TYPE = "hold_test_experiment"
HOLD_DYNAMIC_EXPERIMENT_TYPE = "hold_test_dynamic_experiment"


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

    async def _create_experiment(self, db, experiment_manager, experiment_type: str, name: str):
        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type=experiment_type, name=name, owner="test")
        )
        await experiment_manager.start_experiment(db, name)

    async def _complete_task(self, db, task_manager, task_name: str, experiment_name: str):
        await task_manager.create_task(db, TaskSubmission(name=task_name, type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, task_name)
        await task_manager.complete_task(db, experiment_name, task_name)

    async def _spin_cycle(self, db, scheduler: AbstractScheduler) -> dict[str, dict[str, ScheduledTask]]:
        """Run one scheduling cycle for all registered experiments."""
        result: dict[str, dict[str, ScheduledTask]] = {}
        for name in list(scheduler._registered_experiments.keys()):
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
            for exp_name, tasks in all_tasks.items():
                for task_name, _task in tasks.items():
                    if (exp_name, task_name) not in completed_set:
                        newly_scheduled.append((exp_name, task_name))

            if not newly_scheduled:
                all_done = True
                for name in list(scheduler._registered_experiments.keys()):
                    if not await scheduler.is_experiment_completed(db, name):
                        all_done = False
                        break
                if all_done:
                    break
                continue

            for exp_name, task_name in newly_scheduled:
                await self._complete_task(db, task_manager, task_name, exp_name)
                completed_set.add((exp_name, task_name))
                completed_order.append((exp_name, task_name))

        return completed_order


@pytest.mark.parametrize("setup_lab_experiment", [("abstract_lab", HOLD_EXPERIMENT_TYPE)], indirect=True)
class TestSchedulerHold(_HoldTestBase):
    @pytest.mark.asyncio
    async def test_hold_prevents_device_stealing(
        self, db, scheduler, configuration_manager, experiment_manager, task_manager, allocation_manager
    ):
        """D2 is never used by two experiments simultaneously due to hold."""
        await self._init_scheduler(scheduler)
        graph1 = ExperimentGraph(configuration_manager.experiments[HOLD_EXPERIMENT_TYPE])
        graph2 = ExperimentGraph(configuration_manager.experiments[HOLD_EXPERIMENT_TYPE])

        await self._create_experiment(db, experiment_manager, HOLD_EXPERIMENT_TYPE, "exp1")
        await self._create_experiment(db, experiment_manager, HOLD_EXPERIMENT_TYPE, "exp2")
        await scheduler.register_experiment("exp1", HOLD_EXPERIMENT_TYPE, graph1)
        await scheduler.register_experiment("exp2", HOLD_EXPERIMENT_TYPE, graph2)

        completed_order = await self._spin_and_complete_all(db, scheduler, task_manager)

        exp1_tasks = [t for e, t in completed_order if e == "exp1"]
        exp2_tasks = [t for e, t in completed_order if e == "exp2"]
        assert set(exp1_tasks) == {"setup", "process", "cleanup"}
        assert set(exp2_tasks) == {"setup", "process", "cleanup"}

        # The hold chain on D2 means one experiment must complete before the other starts
        exp1_indices = [i for i, (e, _) in enumerate(completed_order) if e == "exp1"]
        exp2_indices = [i for i, (e, _) in enumerate(completed_order) if e == "exp2"]

        assert max(exp1_indices) < min(exp2_indices) or max(exp2_indices) < min(exp1_indices), (
            f"D2 tasks interleaved between experiments! Order: {completed_order}"
        )

    @pytest.mark.asyncio
    async def test_no_hold_device_released(
        self, db, scheduler, configuration_manager, experiment_manager, task_manager, allocation_manager
    ):
        """D1 (no hold) is released after setup. D2 (hold=true) is held."""
        await self._init_scheduler(scheduler)
        graph = ExperimentGraph(configuration_manager.experiments[HOLD_EXPERIMENT_TYPE])

        await self._create_experiment(db, experiment_manager, HOLD_EXPERIMENT_TYPE, "exp1")
        await scheduler.register_experiment("exp1", HOLD_EXPERIMENT_TYPE, graph)

        for _ in range(10):
            all_tasks = await self._spin_cycle(db, scheduler)
            if "setup" in all_tasks.get("exp1", {}):
                await self._complete_task(db, task_manager, "setup", "exp1")
                break

        await self._spin_cycle(db, scheduler)

        d1_owner = scheduler._device_index.get(("abstract_lab", "D1"))
        d2_owner = scheduler._device_index.get(("abstract_lab", "D2"))

        assert d1_owner is None, f"D1 should be released (no hold), but owned by {d1_owner}"
        assert d2_owner is not None, "D2 should be held"
        assert d2_owner.experiment_name == "exp1", "D2 should be held by exp1"

    @pytest.mark.asyncio
    async def test_hold_cleanup_on_unregister(
        self, db, scheduler, configuration_manager, experiment_manager, task_manager, allocation_manager
    ):
        """Held locks are cleaned up when experiment is unregistered."""
        await self._init_scheduler(scheduler)
        graph = ExperimentGraph(configuration_manager.experiments[HOLD_EXPERIMENT_TYPE])

        await self._create_experiment(db, experiment_manager, HOLD_EXPERIMENT_TYPE, "exp1")
        await scheduler.register_experiment("exp1", HOLD_EXPERIMENT_TYPE, graph)

        for _ in range(10):
            all_tasks = await self._spin_cycle(db, scheduler)
            if "setup" in all_tasks.get("exp1", {}):
                await self._complete_task(db, task_manager, "setup", "exp1")
                break

        await self._spin_cycle(db, scheduler)

        assert scheduler._device_index.get(("abstract_lab", "D2")) is not None

        await scheduler.unregister_experiment(db, "exp1")

        assert scheduler._device_index.get(("abstract_lab", "D2")) is None

    @pytest.mark.asyncio
    async def test_hold_on_terminal_task_released(
        self, db, scheduler, configuration_manager, experiment_manager, task_manager, allocation_manager
    ):
        """Hold on the last task in the DAG is released immediately (no successors)."""
        await self._init_scheduler(scheduler)
        graph = ExperimentGraph(configuration_manager.experiments[HOLD_EXPERIMENT_TYPE])

        await self._create_experiment(db, experiment_manager, HOLD_EXPERIMENT_TYPE, "exp1")
        await scheduler.register_experiment("exp1", HOLD_EXPERIMENT_TYPE, graph)

        # Manually set hold on the cleanup task (terminal node)
        cleanup_task = graph.get_task("cleanup")
        cleanup_task.device_holds["held_device"] = True

        # Run all tasks to completion
        completed_order = await self._spin_and_complete_all(db, scheduler, task_manager)

        assert {t for _, t in completed_order} == {"setup", "process", "cleanup"}

        # D2 should NOT be held after cleanup (no successors)
        d2_owner = scheduler._device_index.get(("abstract_lab", "D2"))
        assert d2_owner is None, f"D2 should be released after terminal task, but owned by {d2_owner}"


@pytest.mark.parametrize("setup_lab_experiment", [("abstract_lab", HOLD_DYNAMIC_EXPERIMENT_TYPE)], indirect=True)
class TestSchedulerDynamicHold(_HoldTestBase):
    @pytest.mark.asyncio
    async def test_dynamic_hold_prevents_device_stealing(
        self, db, scheduler, configuration_manager, experiment_manager, task_manager, allocation_manager
    ):
        """Dynamically assigned D2 is never used by two experiments simultaneously due to hold."""
        await self._init_scheduler(scheduler)
        graph1 = ExperimentGraph(configuration_manager.experiments[HOLD_DYNAMIC_EXPERIMENT_TYPE])
        graph2 = ExperimentGraph(configuration_manager.experiments[HOLD_DYNAMIC_EXPERIMENT_TYPE])

        await self._create_experiment(db, experiment_manager, HOLD_DYNAMIC_EXPERIMENT_TYPE, "exp1")
        await self._create_experiment(db, experiment_manager, HOLD_DYNAMIC_EXPERIMENT_TYPE, "exp2")
        await scheduler.register_experiment("exp1", HOLD_DYNAMIC_EXPERIMENT_TYPE, graph1)
        await scheduler.register_experiment("exp2", HOLD_DYNAMIC_EXPERIMENT_TYPE, graph2)

        completed_order = await self._spin_and_complete_all(db, scheduler, task_manager)

        exp1_tasks = [t for e, t in completed_order if e == "exp1"]
        exp2_tasks = [t for e, t in completed_order if e == "exp2"]
        assert set(exp1_tasks) == {"setup", "process", "cleanup"}
        assert set(exp2_tasks) == {"setup", "process", "cleanup"}

        exp1_indices = [i for i, (e, _) in enumerate(completed_order) if e == "exp1"]
        exp2_indices = [i for i, (e, _) in enumerate(completed_order) if e == "exp2"]

        assert max(exp1_indices) < min(exp2_indices) or max(exp2_indices) < min(exp1_indices), (
            f"D2 tasks interleaved between experiments! Order: {completed_order}"
        )

    @pytest.mark.asyncio
    async def test_dynamic_hold_device_released_vs_held(
        self, db, scheduler, configuration_manager, experiment_manager, task_manager, allocation_manager
    ):
        """D1 (static, no hold) is released after setup. D2 (dynamic, hold=true) is held."""
        await self._init_scheduler(scheduler)
        graph = ExperimentGraph(configuration_manager.experiments[HOLD_DYNAMIC_EXPERIMENT_TYPE])

        await self._create_experiment(db, experiment_manager, HOLD_DYNAMIC_EXPERIMENT_TYPE, "exp1")
        await scheduler.register_experiment("exp1", HOLD_DYNAMIC_EXPERIMENT_TYPE, graph)

        for _ in range(10):
            all_tasks = await self._spin_cycle(db, scheduler)
            if "setup" in all_tasks.get("exp1", {}):
                await self._complete_task(db, task_manager, "setup", "exp1")
                break

        await self._spin_cycle(db, scheduler)

        d1_owner = scheduler._device_index.get(("abstract_lab", "D1"))
        d2_owner = scheduler._device_index.get(("abstract_lab", "D2"))

        assert d1_owner is None, f"D1 should be released (no hold), but owned by {d1_owner}"
        assert d2_owner is not None, "D2 should be held (dynamic assignment with hold=true)"
        assert d2_owner.experiment_name == "exp1", "D2 should be held by exp1"
