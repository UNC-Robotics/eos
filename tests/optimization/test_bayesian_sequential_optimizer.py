import pandas as pd
import pytest
from bofire.data_models.acquisition_functions.acquisition_function import qLogNEI, qLogNEHVI
from bofire.data_models.enum import SamplingMethodEnum
from bofire.data_models.features.continuous import ContinuousInput, ContinuousOutput
from bofire.data_models.objectives.identity import MaximizeObjective, MinimizeObjective

from eos.optimization.sequential_bayesian_optimizer import BayesianSequentialOptimizer


class TestCampaignBayesianOptimizer:
    @pytest.mark.slow
    def test_single_objective_optimization(self):
        optimizer = BayesianSequentialOptimizer(
            inputs=[
                ContinuousInput(key="x", bounds=(0, 7)),
            ],
            outputs=[ContinuousOutput(key="y", objective=MaximizeObjective(w=1.0))],
            constraints=[],
            acquisition_function=qLogNEI(),
            num_initial_samples=2,
            initial_sampling_method=SamplingMethodEnum.SOBOL,
        )

        for _ in range(5):
            parameters = optimizer.sample()
            results = pd.DataFrame()
            results["y"] = -((parameters["x"] - 2) ** 2) + 4
            optimizer.report(parameters, results)

        optimal_solutions = optimizer.get_optimal_solutions()
        assert len(optimal_solutions) == 1
        assert abs(optimal_solutions["y"].to_numpy()[0] - 4) < 0.12

    @pytest.mark.slow
    def test_competing_multi_objective_optimization(self):
        optimizer = BayesianSequentialOptimizer(
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
        )

        for _ in range(10):
            parameters = optimizer.sample()
            results = pd.DataFrame()
            results["y1"] = -((parameters["x"] - 2) ** 2) + 4  # Objective 1: Maximize y1
            results["y2"] = (parameters["x"] - 5) ** 2  # Objective 2: Minimize y2
            optimizer.report(parameters, results)

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
