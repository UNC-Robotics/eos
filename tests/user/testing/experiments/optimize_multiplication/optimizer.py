from bofire.data_models.acquisition_functions.acquisition_function import qLogNEI
from bofire.data_models.enum import SamplingMethodEnum
from bofire.data_models.features.continuous import ContinuousOutput
from bofire.data_models.features.discrete import DiscreteInput
from bofire.data_models.objectives.identity import MinimizeObjective

from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.optimization.beacon_optimizer import BeaconOptimizer


def eos_create_campaign_optimizer() -> tuple[dict, type[AbstractSequentialOptimizer]]:
    constructor_args = {
        "inputs": [
            DiscreteInput(key="mult_1.number", values=list(range(2, 34))),
            DiscreteInput(key="mult_1.factor", values=list(range(2, 18))),
            DiscreteInput(key="mult_2.factor", values=list(range(2, 18))),
        ],
        "outputs": [
            ContinuousOutput(key="compute_multiplication_objective.objective", objective=MinimizeObjective(w=1.0)),
        ],
        "constraints": [],
        "acquisition_function": qLogNEI(),
        "num_initial_samples": 5,
        "initial_sampling_method": SamplingMethodEnum.SOBOL,
        "p_bayesian": 1.0,
        "p_ai": 0.0,
    }

    return constructor_args, BeaconOptimizer
