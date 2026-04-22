from bofire.data_models.acquisition_functions.acquisition_function import qLogNEI
from bofire.data_models.enum import SamplingMethodEnum
from bofire.data_models.features.discrete import DiscreteInput
from bofire.data_models.features.continuous import ContinuousOutput
from bofire.data_models.objectives.identity import MinimizeObjective

from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.optimization.beacon_optimizer import BeaconOptimizer


def eos_create_campaign_optimizer() -> tuple[dict, type[AbstractSequentialOptimizer]]:
    constructor_args = {
        "inputs": [
            DiscreteInput(key="mult_1.number", values=[2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33]),
            DiscreteInput(key="mult_1.factor", values=[2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]),
            DiscreteInput(key="mult_2.factor", values=[2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]),
        ],
        "outputs": [
            ContinuousOutput(key="score_multiplication.loss", objective=MinimizeObjective(w=1.0)),
        ],
        "constraints": [
        ],
        "acquisition_function": qLogNEI(),
        "num_initial_samples": 1,
        "initial_sampling_method": SamplingMethodEnum.SOBOL,
        "p_bayesian": 1.0,
        "p_ai": 0.0,
        "ai_model": "claude-agent-sdk:sonnet",
        "ai_retries": 3,
        "ai_history_size": 50,
        "ai_model_settings": {
            "effort": "medium",
        },
    }
    return constructor_args, BeaconOptimizer
