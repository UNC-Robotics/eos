Optimizers
==========
Optimizers are key to building an autonomous laboratory.
In EOS, optimizers give intelligence to experiment campaigns by optimizing task parameters to achieve objectives over time.
Optimizers in EOS are *sequential*, meaning they iteratively optimize parameters by drawing insights from previous experiments.
One of the most common sequential optimization methods is **Bayesian optimization**, and is especially useful for
optimizing expensive-to-evaluate black box functions.

.. figure:: ../_static/img/optimize-experiment-loop.png
   :alt: Optimization and experiment loop
   :align: center

EOS has a built-in Bayesian optimizer powered by `BoFire <https://experimental-design.github.io/bofire/>`_
(based on `BoTorch <https://botorch.org/>`_).
This optimizer supports both constrained single-objective and multi-objective Bayesian optimization.
It offers several different surrogate models, including Gaussian Processes (GPs) and Multi-Layer Perceptrons (MLPs),
along with various acquisition functions.

Distributed Execution
---------------------
EOS optimizers are created in a dedicated Ray actor process.
This actor process can be created in any computer with an active Ray worker.
This can enable running the optimizer on a more capable computer than the one running the EOS orchestrator.

Optimizer Implementation
------------------------
EOS optimizers are defined in the ``optimizer.py`` file adjacent to ``experiment.yml`` in an EOS package.
Below is an example:

:bdg-primary:`optimizer.py`

.. code-block:: python

    from bofire.data_models.acquisition_functions.acquisition_function import qUCB
    from bofire.data_models.enum import SamplingMethodEnum
    from bofire.data_models.features.continuous import ContinuousOutput, ContinuousInput
    from bofire.data_models.objectives.identity import MinimizeObjective

    from eos.optimization.sequential_bayesian_optimizer import BayesianSequentialOptimizer
    from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer


    def eos_create_campaign_optimizer() -> tuple[dict, type[AbstractSequentialOptimizer]]:
        constructor_args = {
            "inputs": [
                ContinuousInput(key="mix_colors.cyan_volume", bounds=(0, 25)),
                ContinuousInput(key="mix_colors.cyan_strength", bounds=(2, 100)),
                ContinuousInput(key="mix_colors.magenta_volume", bounds=(0, 25)),
                ContinuousInput(key="mix_colors.magenta_strength", bounds=(2, 100)),
                ContinuousInput(key="mix_colors.yellow_volume", bounds=(0, 25)),
                ContinuousInput(key="mix_colors.yellow_strength", bounds=(2, 100)),
                ContinuousInput(key="mix_colors.black_volume", bounds=(0, 25)),
                ContinuousInput(key="mix_colors.black_strength", bounds=(2, 100)),
                ContinuousInput(key="mix_colors.mixing_time", bounds=(1, 45)),
                ContinuousInput(key="mix_colors.mixing_speed", bounds=(100, 200)),
            ],
            "outputs": [
                ContinuousOutput(key="score_color.loss", objective=MinimizeObjective(w=1.0)),
            ],
            "constraints": [],
            "acquisition_function": qUCB(beta=1),
            "num_initial_samples": 25,
            "initial_sampling_method": SamplingMethodEnum.SOBOL,
        }

        return constructor_args, BayesianSequentialOptimizer

Each ``optimizer.py`` file must contain the function ``eos_create_campaign_optimizer``.
This function must return:

#. The constructor arguments to make an optimizer class instance
#. The class type of the optimizer

In this example, we use EOS' built-in Bayesian optimizer.
However, it is also possible to define custom optimizers in this file, and simply return the constructor arguments and
the class type from ``eos_create_campaign_optimizer``.

.. note::
    All optimizers must inherit from the class ``AbstractSequentialOptimizer`` under the ``eos.optimization`` module.

Input and Output Parameter Naming
"""""""""""""""""""""""""""""""""
The names of input and output parameters must reference task parameters.
The EOS reference format must be used:

**TASK.PARAMETER_NAME**

This is necessary for EOS to be able to associate the optimizer with the experiment tasks and to forward parameter values
where needed.

Example Custom Optimizer
------------------------
Below is an example of a custom optimizer implementation that randomly samples parameters for the same color mixing problem:

:bdg-primary:`optimizer.py`

.. code-block:: python

    import random
    from dataclasses import dataclass
    from enum import Enum
    import pandas as pd

    from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer


    class ObjectiveType(Enum):
        MINIMIZE = 1
        MAXIMIZE = 2


    @dataclass
    class Parameter:
        name: str
        lower_bound: float
        upper_bound: float


    @dataclass
    class Metric:
        name: str
        objective: ObjectiveType


    class RandomSamplingOptimizer(AbstractSequentialOptimizer):
        def __init__(self, parameters: list[Parameter], metrics: list[Metric]):
            self.parameters = parameters
            self.metrics = metrics
            self.results: list[dict] = []

        def sample(self, num_experiments: int = 1) -> pd.DataFrame:
            samples = []
            for _ in range(num_experiments):
                sample = {p.name: random.uniform(p.lower_bound, p.upper_bound) for p in self.parameters}
                samples.append(sample)
            return pd.DataFrame(samples)

        def report(self, inputs_df: pd.DataFrame, outputs_df: pd.DataFrame) -> None:
            for _, row in pd.concat([inputs_df, outputs_df], axis=1).iterrows():
                self.results.append(row.to_dict())

        def get_optimal_solutions(self) -> pd.DataFrame:
            if not self.results:
                return pd.DataFrame(
                    columns=[p.name for p in self.parameters] + [m.name for m in self.metrics]
                )
            df = pd.DataFrame(self.results)
            optimal_solutions = []
            for m in self.metrics:
                if m.objective == ObjectiveType.MINIMIZE:
                    optimal = df.loc[df[m.name].idxmin()]
                else:
                    optimal = df.loc[df[m.name].idxmax()]
                optimal_solutions.append(optimal)
            return pd.DataFrame(optimal_solutions)

        def get_input_names(self) -> list[str]:
            return [p.name for p in self.parameters]

        def get_output_names(self) -> list[str]:
            return [m.name for m in self.metrics]

        def get_num_samples_reported(self) -> int:
            return len(self.results)

    def eos_create_campaign_optimizer() -> tuple[dict, type[AbstractSequentialOptimizer]]:
        constructor_args = {
            "parameters": [
                Parameter(name="mix_colors.cyan_volume", lower_bound=0, upper_bound=25),
                Parameter(name="mix_colors.cyan_strength", lower_bound=2, upper_bound=100),
                Parameter(name="mix_colors.magenta_volume", lower_bound=0, upper_bound=25),
                Parameter(name="mix_colors.magenta_strength", lower_bound=2, upper_bound=100),
                Parameter(name="mix_colors.yellow_volume", lower_bound=0, upper_bound=25),
                Parameter(name="mix_colors.yellow_strength", lower_bound=2, upper_bound=100),
                Parameter(name="mix_colors.black_volume", lower_bound=0, upper_bound=25),
                Parameter(name="mix_colors.black_strength", lower_bound=2, upper_bound=100),
                Parameter(name="mix_colors.mixing_time", lower_bound=1, upper_bound=45),
                Parameter(name="mix_colors.mixing_speed", lower_bound=100, upper_bound=200),
            ],
            "metrics": [
                Metric(name="score_color.loss", objective=ObjectiveType.MINIMIZE),
            ],
        }
        return constructor_args, RandomSamplingOptimizer