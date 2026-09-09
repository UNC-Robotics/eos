"""Exercise Beacon's complete sample/report state with a deterministic AI boundary."""

from unittest.mock import AsyncMock

import pandas as pd
import pytest

from tests.optimization.test_beacon_optimizer import TestCustomOptimizer as CustomOptimizerFactory


async def test_beacon_state_through_optimization_and_ai_fallback():
    optimizer = CustomOptimizerFactory()._make(ai_history_size=2, ai_additional_parameters=["context"])

    assert optimizer.get_num_samples_reported() == 0
    assert optimizer.get_meta()["journal"] == []
    assert optimizer._get_best_results() == []

    optimizer.add_insight("Search near x=2")

    # A custom optimizer batch completes out of order.
    first = await optimizer.sample()
    optimizer.set_runtime_params({"value": 2.0})
    second = await optimizer.sample()
    for parameters in [second, first]:
        await optimizer.report(parameters, pd.DataFrame({"y": 4 - (parameters.x - 2) ** 2, "context": "ok"}))

    assert optimizer.get_num_samples_reported() == 2
    assert optimizer._sample_journals == []
    assert optimizer._history[0]["x"] == 2
    assert optimizer._history[0]["context"] == "ok"
    assert "context" not in optimizer.get_optimal_solutions()
    assert optimizer.get_meta()["insights"] == ["Search near x=2"]

    agent = AsyncMock()
    agent.suggest_async.return_value = (pd.DataFrame({"x": [2.1]}), "Test the optimum neighborhood")
    optimizer._ai_agent = agent
    optimizer._p_ai = 1.0
    parameters = await optimizer.sample()

    assert agent.suggest_async.call_args.args[3] == ["Search near x=2"]
    assert agent.suggest_async.call_args.kwargs["total_runs"] == 2
    assert len(agent.suggest_async.call_args.args[1]) == 2
    assert optimizer.get_meta()["insights"] == []
    await optimizer.report(parameters, pd.DataFrame({"y": [3.99], "context": ["AI"]}))

    assert optimizer._history[-1]["_beacon"]["journal"] == "Test the optimum neighborhood"
    assert len(optimizer._history) == 2
    assert optimizer.get_num_samples_reported() == 3
    assert optimizer._sample_journals == []

    optimizer.add_insight("Keep this insight if AI fails")
    agent.suggest_async.side_effect = RuntimeError("Synthetic provider failure")
    parameters = await optimizer.sample()
    assert parameters.x.tolist() == [2.0]
    assert optimizer.get_meta()["insights"] == ["Keep this insight if AI fails"]
    await optimizer.report(parameters, pd.DataFrame({"y": [4.0]}))

    assert "_beacon" not in optimizer._history[-1]
    assert optimizer.get_num_samples_reported() == 4
    assert optimizer._sample_journals == []

    optimizer.set_runtime_params({"p_bayesian": 1.0})
    assert optimizer._ai_agent is None
    assert optimizer.get_runtime_params()["p_ai"] == 0


async def test_beacon_meta_round_trip_restores_runtime_settings():
    optimizer = CustomOptimizerFactory()._make()
    optimizer.set_runtime_params({"value": 2.0, "ai_history_size": 3, "ai_additional_context": "test context"})
    optimizer.add_insight("Preserve on resume")

    restored = CustomOptimizerFactory()._make()
    restored.restore_meta(optimizer.get_meta())

    assert restored.get_meta() == optimizer.get_meta()


def test_beacon_p_ai_runtime_update():
    optimizer = CustomOptimizerFactory()._make()

    # Both probabilities are advertised by get_runtime_params().
    optimizer._create_ai_agent = AsyncMock
    optimizer.set_runtime_params({"p_ai": 1.0})

    assert optimizer.get_runtime_params()["p_ai"] == 1.0
    assert optimizer.get_runtime_params()["p_bayesian"] == 0.0
    assert optimizer._ai_agent is not None


@pytest.mark.parametrize(
    "params",
    [
        {"p_ai": -0.1},
        {"p_ai": float("nan")},
        {"p_bayesian": 1.1},
        {"p_bayesian": 0.2, "p_ai": 0.2},
        {"p_bayesian": 0.0, "ai_history_size": 0},
    ],
)
def test_invalid_runtime_update_preserves_state(params):
    optimizer = CustomOptimizerFactory()._make()
    original = optimizer.get_meta()

    with pytest.raises(ValueError, match=r"p_bayesian|ai_history_size"):
        optimizer.set_runtime_params(params)

    assert optimizer.get_meta() == original
    assert optimizer._ai_agent is None


async def test_history_limit_applies_immediately_and_metadata_is_a_snapshot():
    optimizer = CustomOptimizerFactory()._make()

    for value in [1.0, 2.0, 3.0]:
        optimizer.set_runtime_params({"value": value})
        inputs = await optimizer.sample()
        await optimizer.report(inputs, pd.DataFrame({"y": [value]}))

    optimizer.set_runtime_params({"ai_history_size": 1})

    assert [entry["x"] for entry in optimizer._history] == [3.0]
    assert optimizer.get_num_samples_reported() == 3

    optimizer.add_insight("Original insight")
    snapshot = optimizer.get_meta()
    restored = CustomOptimizerFactory()._make()
    restored.restore_meta(snapshot)
    restored.add_insight("New insight")

    assert optimizer.get_meta() == snapshot
    assert snapshot["insights"] == ["Original insight"]
    assert snapshot["journal"] == ["Expert insight received: Original insight"]
