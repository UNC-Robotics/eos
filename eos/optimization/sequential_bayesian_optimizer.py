import bofire.strategies.api as strategies
import pandas as pd
from bofire.data_models.acquisition_functions.acquisition_function import (
    AcquisitionFunction,
)
from bofire.data_models.constraints.constraint import Constraint
from bofire.data_models.domain.constraints import Constraints
from bofire.data_models.domain.domain import Domain
from bofire.data_models.domain.features import Inputs, Outputs
from bofire.data_models.enum import SamplingMethodEnum
from bofire.data_models.features.categorical import CategoricalInput, CategoricalOutput
from bofire.data_models.features.continuous import ContinuousInput, ContinuousOutput
from bofire.data_models.features.discrete import DiscreteInput
from bofire.data_models.objectives.identity import MaximizeObjective, MinimizeObjective
from bofire.data_models.objectives.target import CloseToTargetObjective
from bofire.data_models.strategies.predictives.mobo import MoboStrategy
from bofire.data_models.strategies.predictives.sobo import SoboStrategy
from bofire.data_models.surrogates.api import BotorchSurrogates
from pandas import Series

from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.optimization.exceptions import EosCampaignOptimizerDomainError


class BayesianSequentialOptimizer(AbstractSequentialOptimizer):
    """
    Uses BoFire's Bayesian optimization to optimize the parameters of a series of protocols.
    """

    InputType = ContinuousInput | DiscreteInput | CategoricalInput
    OutputType = ContinuousOutput | CategoricalOutput

    def __init__(
        self,
        inputs: list[InputType],
        outputs: list[OutputType],
        constraints: list[Constraint],
        acquisition_function: AcquisitionFunction,
        num_initial_samples: int,
        initial_sampling_method: SamplingMethodEnum = SamplingMethodEnum.SOBOL,
        surrogate_specs: BotorchSurrogates | None = None,
    ):
        self._acquisition_function: AcquisitionFunction = acquisition_function
        self._num_initial_samples: int = num_initial_samples
        self._initial_sampling_method: SamplingMethodEnum = initial_sampling_method
        self._domain: Domain = Domain(
            inputs=Inputs(features=inputs),
            outputs=Outputs(features=outputs),
            constraints=Constraints(constraints=constraints),
        )
        self._input_names = [input_feature.key for input_feature in self._domain.inputs.features]
        self._output_names = [output_feature.key for output_feature in self._domain.outputs.features]

        self._generate_initial_samples: bool = self._num_initial_samples > 0
        self._initial_samples_df: pd.DataFrame | None = None
        self._num_samples_reported: int = 0

        strategy_kwargs = {
            "domain": self._domain,
            "acquisition_function": acquisition_function,
        }
        if surrogate_specs is not None:
            strategy_kwargs["surrogate_specs"] = surrogate_specs

        self._optimizer_data_model = (
            SoboStrategy(**strategy_kwargs) if len(outputs) == 1 else MoboStrategy(**strategy_kwargs)
        )
        self._optimizer = strategies.map(data_model=self._optimizer_data_model)

    def sample(self, num_protocol_runs: int = 1) -> pd.DataFrame:
        if self._generate_initial_samples and self._num_samples_reported < self._num_initial_samples:
            if self._initial_samples_df is None:
                self._generate_initial_samples_df()

            if self._initial_samples_df is not None and not self._initial_samples_df.empty:
                initial = self._fetch_and_remove_initial_samples(num_protocol_runs)
                if len(initial) >= num_protocol_runs:
                    return initial
                remaining = num_protocol_runs - len(initial)
                extra = self._sample_constrained(remaining)
                return pd.concat([initial, extra], ignore_index=True)

            self._initial_samples_df = None
            return self._sample_constrained(num_protocol_runs)

        try:
            new_parameters_df = self._optimizer.ask(candidate_count=num_protocol_runs, add_pending=True)
        except ValueError as e:
            if "Not enough experiments" in str(e):
                return self._sample_constrained(num_protocol_runs)
            raise

        return new_parameters_df[self._input_names]

    def _generate_initial_samples_df(self) -> None:
        self._initial_samples_df = self._sample_constrained(self._num_initial_samples)

    def _sample_constrained(self, n: int, max_attempts: int = 100, oversample_factor: int = 10) -> pd.DataFrame:
        """Generate samples that satisfy all domain constraints via rejection sampling.

        Oversamples by `oversample_factor`, filters to feasible rows, and repeats
        until `n` feasible samples are collected or `max_attempts` is reached.
        """
        if not self._domain.constraints.constraints:
            return self._domain.inputs.sample(n=n, method=self._initial_sampling_method)

        feasible = pd.DataFrame()
        for _ in range(max_attempts):
            batch_size = (n - len(feasible)) * oversample_factor
            candidates = self._domain.inputs.sample(n=batch_size, method=self._initial_sampling_method)
            valid = self._domain.is_fulfilled(candidates)
            feasible = pd.concat([feasible, candidates[valid]], ignore_index=True)
            if len(feasible) >= n:
                return feasible.iloc[:n]

        if len(feasible) > 0:
            return feasible.iloc[: min(n, len(feasible))]

        raise ValueError(
            f"Could not generate {n} feasible initial samples after {max_attempts} attempts. "
            f"The constraint-feasible region may be too small relative to the input bounds."
        )

    def _fetch_and_remove_initial_samples(self, num_protocol_runs: int) -> pd.DataFrame:
        num_protocol_runs = min(num_protocol_runs, len(self._initial_samples_df))
        new_parameters_df = self._initial_samples_df.iloc[:num_protocol_runs]
        self._initial_samples_df = self._initial_samples_df.iloc[num_protocol_runs:]
        return new_parameters_df

    def report(self, inputs_df: pd.DataFrame, outputs_df: pd.DataFrame) -> None:
        self._validate_sample(inputs_df, outputs_df)
        results_df = pd.concat([inputs_df, outputs_df], axis=1)
        self._optimizer.tell(results_df)
        self._clear_reported_pending(inputs_df)
        self._num_samples_reported += len(results_df)

    def _clear_reported_pending(self, inputs_df: pd.DataFrame) -> None:
        """
        Remove reported inputs from BoFire's pending candidates.

        When results arrive for previously sampled points, those points are no longer
        pending — the surrogate model now has their actual outcomes.
        """
        if self._optimizer.candidates is None or self._optimizer.candidates.empty:
            return
        pending = self._optimizer.candidates
        merged = pending.merge(
            inputs_df[self._input_names],
            on=self._input_names,
            how="left",
            indicator=True,
        )
        remaining = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])
        if remaining.empty:
            self._optimizer.reset_candidates()
        else:
            self._optimizer.set_candidates(remaining)

    def get_optimal_solutions(self) -> pd.DataFrame:
        completed_runs = self._optimizer.experiments  # bofire API returns completed runs
        outputs = self._domain.outputs.get_by_objective(
            includes=[MaximizeObjective, MinimizeObjective, CloseToTargetObjective]
        ).features

        def is_dominated(row: Series, other_row: Series) -> bool:
            at_least_one_worse = False
            for output in outputs:
                if isinstance(output.objective, MaximizeObjective):
                    if row[output.key] > other_row[output.key]:
                        return False
                    if row[output.key] < other_row[output.key]:
                        at_least_one_worse = True
                elif isinstance(output.objective, MinimizeObjective):
                    if row[output.key] < other_row[output.key]:
                        return False
                    if row[output.key] > other_row[output.key]:
                        at_least_one_worse = True
                elif isinstance(output.objective, CloseToTargetObjective):
                    target = output.objective.target
                    if abs(row[output.key] - target) < abs(other_row[output.key] - target):
                        return False
                    if abs(row[output.key] - target) > abs(other_row[output.key] - target):
                        at_least_one_worse = True
            return at_least_one_worse

        pareto_solutions = [
            row
            for i, row in completed_runs.iterrows()
            if not any(is_dominated(row, other_row) for j, other_row in completed_runs.iterrows() if i != j)
        ]

        result_df = pd.DataFrame(pareto_solutions)

        # 'valid_' columns are generated by BoFire
        filtered_columns = [col for col in result_df.columns if not col.startswith("valid_")]

        return result_df[filtered_columns]

    def get_input_names(self) -> list[str]:
        return self._input_names

    def get_output_names(self) -> list[str]:
        return self._output_names

    def get_num_samples_reported(self) -> int:
        return self._num_samples_reported

    def _get_output(self, output_name: str) -> OutputType:
        for output in self._domain.outputs.features:
            if output.key == output_name:
                return output

        raise EosCampaignOptimizerDomainError(f"Output {output_name} not found in the optimization domain.")

    def _validate_sample(self, inputs_df: pd.DataFrame, outputs_df: pd.DataFrame) -> None:
        """
        Validate that all expected input and output columns are present in their respective DataFrames.

        :param inputs_df: DataFrame with input parameters for the protocols.
        :param outputs_df: DataFrame with output parameters for the protocols.
        :raises EosCampaignOptimizerDomainError: If any expected input or output columns are missing.
        """
        missing_inputs = set(self._input_names) - set(inputs_df.columns)
        missing_outputs = set(self._output_names) - set(outputs_df.columns)

        if missing_inputs or missing_outputs:
            error_message = []
            if missing_inputs:
                error_message.append(f"Missing input columns: {', '.join(missing_inputs)}")
            if missing_outputs:
                error_message.append(f"Missing output columns: {', '.join(missing_outputs)}")
            raise EosCampaignOptimizerDomainError(". ".join(error_message))
