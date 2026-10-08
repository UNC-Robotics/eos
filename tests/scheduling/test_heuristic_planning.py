import time

from eos.configuration.protocol_graph import ProtocolGraph
from eos.scheduling import simulation
from tests.fixtures import *

PROTOCOL = "run_if"


@pytest.mark.parametrize("setup_lab_protocol", [("multiplication_lab", PROTOCOL)], indirect=True)
class TestHeuristicPlanning:
    async def test_seed_rollouts_respect_the_time_budget(
        self,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        device_manager,
        allocation_manager,
        monkeypatch,
    ):
        scheduler = HeuristicScheduler(
            configuration_manager, protocol_run_manager, task_manager, device_manager, allocation_manager
        )
        for i in range(3):
            graph = ProtocolGraph(configuration_manager.protocols[PROTOCOL])
            await scheduler.register_protocol_run(f"plan_{i}", PROTOCOL, graph)
        instances = [scheduler._build_instance(f"plan_{i}", set(), 0) for i in range(3)]

        rollout = simulation._rollout

        def slow_rollout(*args):
            time.sleep(0.2)
            return rollout(*args)

        monkeypatch.setattr(simulation, "_rollout", slow_rollout)
        start = time.perf_counter()
        plan = simulation.plan_priorities(configuration_manager.labs, instances, time_budget_s=0.05)

        assert plan.rollouts == 1
        assert plan.priorities
        assert time.perf_counter() - start < 0.4
