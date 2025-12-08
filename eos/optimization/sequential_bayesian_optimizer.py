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
    Uses BoFire's Bayesian optimization to optimize the parameters of a series of experiments.
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

    def sample(self, num_experiments: int = 1) -> pd.DataFrame:
        if self._generate_initial_samples and self._num_samples_reported < self._num_initial_samples:
            if self._initial_samples_df is None:
                self._generate_initial_samples_df()

            if self._initial_samples_df is not None and not self._initial_samples_df.empty:
                return self._fetch_and_remove_initial_samples(num_experiments)

            self._initial_samples_df = None

        new_parameters_df = self._optimizer.ask(candidate_count=num_experiments)

        return new_parameters_df[self._input_names]

    def _generate_initial_samples_df(self) -> None:
        self._initial_samples_df = self._domain.inputs.sample(
            n=self._num_initial_samples, method=self._initial_sampling_method
        )

    def _fetch_and_remove_initial_samples(self, num_experiments: int) -> pd.DataFrame:
        num_experiments = min(num_experiments, len(self._initial_samples_df))
        new_parameters_df = self._initial_samples_df.iloc[:num_experiments]
        self._initial_samples_df = self._initial_samples_df.iloc[num_experiments:]
        return new_parameters_df

    def report(self, inputs_df: pd.DataFrame, outputs_df: pd.DataFrame) -> None:
        self._validate_sample(inputs_df, outputs_df)
        results_df = pd.concat([inputs_df, outputs_df], axis=1)
        self._optimizer.tell(results_df)
        self._num_samples_reported += len(results_df)

    def get_optimal_solutions(self) -> pd.DataFrame:
        experiments = self._optimizer.experiments
        outputs = self._domain.outputs.get_by_objective(
            includes=[MaximizeObjective, MinimizeObjective, CloseToTargetObjective]
        ).features

        def is_dominated(exp: Series, other_exp: Series) -> bool:
            at_least_one_worse = False
            for output in outputs:
                if isinstance(output.objective, MaximizeObjective):
                    if exp[output.key] > other_exp[output.key]:
                        return False
                    if exp[output.key] < other_exp[output.key]:
                        at_least_one_worse = True
                elif isinstance(output.objective, MinimizeObjective):
                    if exp[output.key] < other_exp[output.key]:
                        return False
                    if exp[output.key] > other_exp[output.key]:
                        at_least_one_worse = True
                elif isinstance(output.objective, CloseToTargetObjective):
                    target = output.objective.target
                    if abs(exp[output.key] - target) < abs(other_exp[output.key] - target):
                        return False
                    if abs(exp[output.key] - target) > abs(other_exp[output.key] - target):
                        at_least_one_worse = True
            return at_least_one_worse

        pareto_solutions = [
            exp
            for i, exp in experiments.iterrows()
            if not any(is_dominated(exp, other_exp) for j, other_exp in experiments.iterrows() if i != j)
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

        :param inputs_df: DataFrame with input parameters for the experiments.
        :param outputs_df: DataFrame with output parameters for the experiments.
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
