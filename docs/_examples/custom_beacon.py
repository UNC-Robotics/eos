"""A discrete grid-search optimizer for the bundled multiplication protocol."""

from itertools import product

import pandas as pd
from bofire.data_models.features.continuous import ContinuousOutput
from bofire.data_models.features.discrete import DiscreteInput
from bofire.data_models.objectives.identity import MinimizeObjective

from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.optimization.beacon_optimizer import BeaconOptimizer


class GridSearchOptimizer(AbstractSequentialOptimizer):
    def __init__(self, inputs, outputs, constraints, descending=False):
        if constraints or not all(isinstance(feature, DiscreteInput) for feature in inputs):
            raise ValueError("This example supports discrete inputs without constraints")
        if len(outputs) != 1 or not isinstance(outputs[0].objective, MinimizeObjective):
            raise ValueError("This example requires one minimization objective")

        self._input_names = [feature.key for feature in inputs]
        self._output_names = [feature.key for feature in outputs]
        self._grid = list(product(*(feature.values for feature in inputs)))
        self._pending = set()
        self._completed = set()
        self._results = []
        self.set_runtime_params({"descending": descending})

    def sample(self, num_protocol_runs=1):
        available = [
            point
            for point in sorted(self._grid, reverse=self._descending)
            if point not in self._completed and point not in self._pending
        ]
        selected = available[:num_protocol_runs]
        if len(selected) != num_protocol_runs:
            raise ValueError("Grid exhausted")

        self._pending.update(selected)
        return pd.DataFrame(selected, columns=self._input_names)

    def report(self, inputs_df, outputs_df):
        rows = pd.concat([inputs_df.reset_index(drop=True), outputs_df.reset_index(drop=True)], axis=1)
        self._results.extend(rows.to_dict(orient="records"))

        for point in inputs_df[self._input_names].itertuples(index=False, name=None):
            self._completed.add(point)
            self._pending.discard(point)

    def get_optimal_solutions(self):
        results = pd.DataFrame(self._results, columns=self._input_names + self._output_names)
        if results.empty:
            return results

        objective = results[self._output_names[0]]
        return results.loc[objective == objective.min()].copy()

    def get_input_names(self):
        return self._input_names

    def get_output_names(self):
        return self._output_names

    def get_num_samples_reported(self):
        return len(self._results)

    def get_runtime_params(self):
        return {"descending": self._descending}

    def set_runtime_params(self, params):
        if "descending" in params:
            if not isinstance(params["descending"], bool):
                raise ValueError("descending must be a boolean")
            self._descending = params["descending"]


class GridBeacon(BeaconOptimizer):
    def __init__(self, descending=False, **kwargs):
        self._descending = descending
        super().__init__(**kwargs)

    def _create_optimizer(self, inputs, outputs, constraints):
        return GridSearchOptimizer(inputs, outputs, constraints, descending=self._descending)

    @classmethod
    def eos_param_schema(cls):
        return [{"key": "descending", "type": "checkbox", "default": False, "runtime": True}]


def eos_create_campaign_optimizer():
    return {
        "inputs": [
            DiscreteInput(key="mult_1.number", values=[4, 8, 16, 32]),
            DiscreteInput(key="mult_1.factor", values=[4, 8, 16]),
            DiscreteInput(key="mult_2.factor", values=[4, 8, 16]),
        ],
        "outputs": [
            ContinuousOutput(key="score_multiplication.loss", objective=MinimizeObjective()),
        ],
        "constraints": [],
        "p_bayesian": 1.0,
        "p_ai": 0.0,
        "ai_additional_parameters": ["mult_2.product"],
    }, GridBeacon
