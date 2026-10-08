from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.scheduling.simulation import (
    bottom_levels,
    _dispatch_rules,
    _rollout,
    _to_ranks,
    LockManager,
    create_protocol_run_instances,
    plan_priorities,
)
from eos.tasks.entities.task import TaskSubmission
from tests.fixtures import *


async def _start_protocol_run(db, protocol_run_manager, protocol: str, name: str) -> None:
    await protocol_run_manager.create_protocol_run(db, ProtocolRunSubmission(type=protocol, name=name, owner="test"))
    await protocol_run_manager.start_protocol_run(db, name)


async def _complete_task(db, task_manager, scheduler, task_name: str, protocol_run_name: str) -> None:
    """Complete a task like the task executor does, which also releases it in the scheduler."""
    await task_manager.create_task(db, TaskSubmission(name=task_name, type="Noop", protocol_run_name=protocol_run_name))
    await task_manager.start_task(db, protocol_run_name, task_name)
    await task_manager.complete_task(db, protocol_run_name, task_name)
    await scheduler.release_task(db, task_name, protocol_run_name)


@pytest.mark.parametrize("setup_lab_protocol", [("abstract_lab", "abstract_protocol")], indirect=True)
class TestHeuristicScheduler:
    @pytest.mark.asyncio
    async def test_correct_schedule(self, db, heuristic_scheduler, protocol_graph, protocol_run_manager, task_manager):
        await _start_protocol_run(db, protocol_run_manager, "abstract_protocol", "run1")
        await heuristic_scheduler.register_protocol_run("run1", "abstract_protocol", protocol_graph)

        expected_batches = [
            {("A", "D2")},
            {("B", "D1"), ("C", "D3")},
            {("D", "D1"), ("E", "D3"), ("F", "D2")},
            {("G", "D5")},
            {("H", "D6")},
        ]
        for expected in expected_batches:
            tasks = await request_tasks(heuristic_scheduler, db, "run1")
            assert {(t.name, next(iter(t.devices.values())).name) for t in tasks} == expected
            for task in tasks:
                await _complete_task(db, task_manager, heuristic_scheduler, task.name, "run1")

        assert await heuristic_scheduler.is_protocol_run_completed(db, "run1")
        assert await request_tasks(heuristic_scheduler, db, "run1") == []

    @pytest.mark.asyncio
    async def test_tasks_dispatched_for_other_runs_are_returned_once(
        self, db, heuristic_scheduler, configuration_manager, protocol_run_manager
    ):
        """One request allocates for every run, and each run receives its tasks on its own request."""
        for name in ["run1", "run2"]:
            await _start_protocol_run(db, protocol_run_manager, "abstract_protocol", name)
            graph = ProtocolGraph(configuration_manager.protocols["abstract_protocol"])
            await heuristic_scheduler.register_protocol_run(name, "abstract_protocol", graph)

        run1_tasks = await request_tasks(heuristic_scheduler, db, "run1")
        owners = {(e.protocol_run_name, e.owner) for e in heuristic_scheduler._device_index.values()}
        run2_tasks = await request_tasks(heuristic_scheduler, db, "run2")

        # Both runs need D2 for task A, so exactly one of them gets it
        assert len(run1_tasks) + len(run2_tasks) == 1
        assert owners == {(t.protocol_run_name, t.name) for t in [*run1_tasks, *run2_tasks]}
        assert await request_tasks(heuristic_scheduler, db, "run1") == []
        assert await request_tasks(heuristic_scheduler, db, "run2") == []


@pytest.mark.parametrize("setup_lab_protocol", [("abstract_lab", "abstract_protocol_2")], indirect=True)
class TestPlanPriorities:
    def test_plan_beats_topological_order(self, setup_lab_protocol, configuration_manager):
        lab, protocol = setup_lab_protocol
        labs = {lab.name: lab}
        instances = create_protocol_run_instances("abstract_protocol_2", protocol, 2)

        plan = plan_priorities(labs, instances, time_budget_s=0.2)

        assert set(plan.priorities) == {(exp.name, t) for exp in instances for t in exp.all_tasks}

        levels = {exp.name: bottom_levels(exp.protocol_graph, exp.tasks) for exp in instances}
        topo = _to_ranks(_dispatch_rules(instances, levels)[0])
        topo_makespan, _ = _rollout(labs, instances, [], LockManager(), topo)
        assert plan.makespan <= topo_makespan
        assert all(not exp.completed_tasks for exp in instances), "planning must not mutate the instances"
