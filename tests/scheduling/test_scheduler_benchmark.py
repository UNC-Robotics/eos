import pytest

from tests.scheduling.benchmark.harness import SCENARIOS, SCHEDULERS, run_scenario

# Short budgets: these tests check correctness, while python -m tests.scheduling.benchmark compares quality
PARAMETERS = {
    "greedy": {},
    "heuristic": {"time_budget_s": 0.1},
    "cpsat": {"max_time_in_seconds": 3.0, "warm_start_budget_s": 0.1},
}


@pytest.fixture(scope="module")
def configuration_managers():
    return {}


@pytest.mark.slow
@pytest.mark.parametrize("scheduler", list(SCHEDULERS))
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: f"{s.size}-{s.name.replace(' ', '_')}")
async def test_scheduler_completes_workload_without_violations(scenario, scheduler, configuration_managers):
    result = await run_scenario(scenario, scheduler, PARAMETERS[scheduler], configuration_managers)
    assert result.error is None
    assert result.violations == []
