import pandas as pd
import pytest
from bofire.data_models.acquisition_functions.acquisition_function import qLogNEI, qLogNEHVI
from bofire.data_models.enum import SamplingMethodEnum
from bofire.data_models.features.continuous import ContinuousInput, ContinuousOutput
from bofire.data_models.objectives.identity import MaximizeObjective, MinimizeObjective

from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.optimization.beacon_ai_agent import _validate_model
from eos.optimization.beacon_optimizer import BeaconOptimizer
from eos.optimization.sequential_bayesian_optimizer import BayesianSequentialOptimizer


class TestBeaconOptimizer:
    @pytest.mark.slow
    async def test_single_objective_optimization(self):
        optimizer = BeaconOptimizer(
            inputs=[
                ContinuousInput(key="x", bounds=(0, 7)),
            ],
            outputs=[ContinuousOutput(key="y", objective=MaximizeObjective(w=1.0))],
            constraints=[],
            acquisition_function=qLogNEI(),
            num_initial_samples=2,
            initial_sampling_method=SamplingMethodEnum.SOBOL,
            p_bayesian=1.0,
            p_ai=0.0,
        )

        for _ in range(8):
            parameters = await optimizer.sample()
            results = pd.DataFrame()
            results["y"] = -((parameters["x"] - 2) ** 2) + 4
            await optimizer.report(parameters, results)

        optimal_solutions = optimizer.get_optimal_solutions()
        assert len(optimal_solutions) == 1
        assert abs(optimal_solutions["y"].to_numpy()[0] - 4) < 0.25

    @pytest.mark.slow
    async def test_competing_multi_objective_optimization(self):
        optimizer = BeaconOptimizer(
            inputs=[
                ContinuousInput(key="x", bounds=(0, 7)),
            ],
            outputs=[
                ContinuousOutput(key="y1", objective=MaximizeObjective(w=1.0)),
                ContinuousOutput(key="y2", objective=MinimizeObjective(w=1.0)),
            ],
            constraints=[],
            acquisition_function=qLogNEHVI(),
            num_initial_samples=2,
            initial_sampling_method=SamplingMethodEnum.SOBOL,
            p_bayesian=1.0,
            p_ai=0.0,
        )

        for _ in range(10):
            parameters = await optimizer.sample()
            results = pd.DataFrame()
            results["y1"] = -((parameters["x"] - 2) ** 2) + 4  # Objective 1: Maximize y1
            results["y2"] = (parameters["x"] - 5) ** 2  # Objective 2: Minimize y2
            await optimizer.report(parameters, results)

        optimal_solutions = optimizer.get_optimal_solutions()
        pd.set_option("display.max_rows", None, "display.max_columns", None)
        print(optimal_solutions)

        # Ensure the solutions are non-dominated and belong to the Pareto front
        for i, solution_i in optimal_solutions.iterrows():
            for j, solution_j in optimal_solutions.iterrows():
                if i != j:
                    assert not (
                        (solution_i["y1"] <= solution_j["y1"] and solution_i["y2"] >= solution_j["y2"])
                        and (solution_i["y1"] < solution_j["y1"] or solution_i["y2"] > solution_j["y2"])
                    )

        # Verify solutions are close to the true Pareto front
        true_pareto_front = [{"x": 2, "y1": 4, "y2": 9}, {"x": 5, "y1": -5, "y2": 0}]

        for true_solution in true_pareto_front:
            assert any(
                abs(solution["x"] - true_solution["x"]) < 2.0
                and abs(solution["y1"] - true_solution["y1"]) < 2.0
                and abs(solution["y2"] - true_solution["y2"]) < 2.0
                for _, solution in optimal_solutions.iterrows()
            )

    async def test_sample_after_initial_samples_exhausted_before_all_reported(self):
        optimizer = BeaconOptimizer(
            inputs=[
                ContinuousInput(key="x", bounds=(0, 7)),
            ],
            outputs=[ContinuousOutput(key="y", objective=MaximizeObjective(w=1.0))],
            constraints=[],
            acquisition_function=qLogNEI(),
            num_initial_samples=5,
            initial_sampling_method=SamplingMethodEnum.SOBOL,
            p_bayesian=1.0,
            p_ai=0.0,
        )

        # Consume all 5 initial samples in one batch
        params_batch = await optimizer.sample(num_protocol_runs=5)
        assert len(params_batch) == 5

        # Report only 1 result (simulating 1 protocol run completing before the others)
        first_params = params_batch.iloc[[0]]
        first_results = pd.DataFrame({"y": -((first_params["x"] - 2) ** 2) + 4})
        await optimizer.report(first_params, first_results)

        # Request 1 more sample to fill the empty slot — this should NOT raise
        extra = await optimizer.sample(num_protocol_runs=1)
        assert len(extra) == 1


class _FixedOptimizer(AbstractSequentialOptimizer):
    """Minimal custom optimizer that always suggests the same point."""

    def __init__(self, inputs, outputs, constraints, value: float = 1.5):
        self._inputs = inputs
        self._outputs = outputs
        self._value = value
        self._results: list[dict] = []

    def sample(self, num_protocol_runs: int = 1) -> pd.DataFrame:
        return pd.DataFrame({f.key: [self._value] * num_protocol_runs for f in self._inputs})

    def report(self, inputs_df: pd.DataFrame, outputs_df: pd.DataFrame) -> None:
        self._results.extend(pd.concat([inputs_df, outputs_df], axis=1).to_dict(orient="records"))

    def get_optimal_solutions(self) -> pd.DataFrame:
        return pd.DataFrame(self._results)

    def get_input_names(self) -> list[str]:
        return [f.key for f in self._inputs]

    def get_output_names(self) -> list[str]:
        return [f.key for f in self._outputs]

    def get_num_samples_reported(self) -> int:
        return len(self._results)

    def get_runtime_params(self) -> dict:
        return {"value": self._value}

    def set_runtime_params(self, params: dict) -> None:
        if "value" in params:
            self._value = float(params["value"])


class _CustomBeacon(BeaconOptimizer):
    """Beacon with the Bayesian half swapped for a custom optimizer."""

    def __init__(self, value: float = 1.5, **kwargs):
        self._value = value
        super().__init__(**kwargs)

    def _create_optimizer(self, inputs, outputs, constraints) -> AbstractSequentialOptimizer:
        return _FixedOptimizer(inputs, outputs, constraints, value=self._value)

    @classmethod
    def eos_param_schema(cls) -> list[dict]:
        return [{"key": "value", "type": "number", "default": 1.5, "min": 0.0, "runtime": True}]


class TestCustomOptimizer:
    def _make(self, **kwargs) -> _CustomBeacon:
        return _CustomBeacon(
            inputs=[ContinuousInput(key="x", bounds=(0, 7))],
            outputs=[ContinuousOutput(key="y", objective=MaximizeObjective(w=1.0))],
            constraints=[],
            p_bayesian=1.0,
            p_ai=0.0,
            **kwargs,
        )

    async def test_sampling_routes_through_custom_optimizer(self):
        """No acquisition_function is needed when the Bayesian half is replaced."""
        optimizer = self._make(value=3.0)

        parameters = await optimizer.sample(num_protocol_runs=2)
        assert parameters["x"].tolist() == [3.0, 3.0]

        results = pd.DataFrame({"y": [1.0, 1.0]})
        await optimizer.report(parameters, results)

        assert optimizer.get_num_samples_reported() == 2
        assert len(optimizer.get_optimal_solutions()) == 2
        assert optimizer.get_input_names() == ["x"]

    def test_runtime_params_merge_and_forward(self):
        optimizer = self._make()

        assert optimizer.get_runtime_params()["value"] == 1.5
        assert optimizer.get_runtime_params()["p_bayesian"] == 1.0

        optimizer.set_runtime_params({"value": 4.0, "ai_history_size": 10})

        assert optimizer.get_runtime_params()["value"] == 4.0
        assert optimizer.get_runtime_params()["ai_history_size"] == 10

    def test_default_acquisition_function_is_required(self):
        with pytest.raises(ValueError, match="acquisition_function"):
            BeaconOptimizer(
                inputs=[ContinuousInput(key="x", bounds=(0, 7))],
                outputs=[ContinuousOutput(key="y", objective=MaximizeObjective(w=1.0))],
                constraints=[],
                p_bayesian=1.0,
                p_ai=0.0,
            )

    def test_param_schema_defaults_to_empty(self):
        assert BayesianSequentialOptimizer.eos_param_schema() == []
        assert _CustomBeacon.eos_param_schema()[0]["key"] == "value"


class TestModelValidation:
    @pytest.mark.parametrize("model", ["claude-agent-sdk:sonnet", "claude-agent-sdk:opus", "ollama:qwen3.5:9b"])
    def test_supported_models_accepted(self, model: str):
        _validate_model(model)

    @pytest.mark.parametrize(
        "model", ["anthropic:claude-sonnet-4-6", "openai:gpt-5.4", "google-gla:gemini-3.1-pro-preview", "sonnet"]
    )
    def test_unsupported_models_rejected(self, model: str):
        with pytest.raises(ValueError, match="Unsupported Beacon AI model"):
            _validate_model(model)
