Campaigns
=========
A campaign in EOS is a protocol executed multiple times in sequence, usually with varying parameters, toward goals such as optimizing objectives by searching for optimal parameters.
Campaigns are the highest-level execution unit in EOS and can be used to implement autonomous (self-driving) labs.

The DMTA loop is a common paradigm in autonomous experimentation, and EOS campaigns can implement it.
EOS has built-in support for running campaigns of a protocol, including a built-in Bayesian optimizer for parameter optimization.

.. figure:: ../_static/img/dmta-loop.png
   :alt: The DMTA Loop
   :align: center

Optimization Setup (Analyze and Design Phases)
----------------------------------------------
Both the "analyze" and "design" phases of the DMTA loop can be automated by optimizing protocol parameters over time.
EOS natively supports this through a built-in Bayesian optimizer that integrates with the campaign execution module.
Custom algorithms such as reinforcement learning can also be incorporated.

The color mixing protocol shows how a campaign with optimization can be set up.
It has ten dynamic parameters, all defined on the "mix_colors" task:

.. code-block:: yaml

    cyan_volume: eos_dynamic
    cyan_strength: eos_dynamic
    magenta_volume: eos_dynamic
    magenta_strength: eos_dynamic
    yellow_volume: eos_dynamic
    yellow_strength: eos_dynamic
    black_volume: eos_dynamic
    black_strength: eos_dynamic
    mixing_time: eos_dynamic
    mixing_speed: eos_dynamic

Looking at the task specification of the ``score_color`` task, we also see that there is an output parameter called "loss".

:bdg-primary:`task.yml`

.. code-block:: yaml

    type: Score Color
    desc: Score a color based on how close it is to an expected color

    input_parameters:
      red:
        type: int
        unit: n/a
        desc: The red component of the color
      green:
        type: int
        unit: n/a
        desc: The green component of the color
      blue:
        type: int
        unit: n/a
        desc: The blue component of the color

    output_parameters:
      loss:
        type: float
        unit: n/a
        desc: Total loss of the color compared to the expected color

This protocol involves selecting CMYK color component volumes, a mixing time, and a mixing speed to minimize the loss of a synthesized color compared to an expected color.

This setup is summarized in the ``optimizer.py`` file adjacent to ``protocol.yml``.

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
            "num_initial_samples": 10,
            "initial_sampling_method": SamplingMethodEnum.SOBOL,
        }

        return constructor_args, BayesianSequentialOptimizer

The ``eos_create_campaign_optimizer`` function creates the campaign optimizer.
The inputs are all the dynamic parameters in the protocol, the output is the "loss" parameter from the "score_color" task, and the objective is to minimize this loss.

More about optimizers can be found in the Optimizers section.

Automation Setup (Make and Test Phases)
---------------------------------------
EOS manages automation execution. Tasks and devices must be implemented by the user, and the protocol must be carefully set up to run autonomously.

Some guidelines:

* Each protocol run should be standalone and not depend on previous runs.
* Each protocol run should leave the lab in a state ready for the next run.
* Minimize dependencies between tasks. A task should depend on another only when necessary.
* Tasks should declare any device they interact with, even if they do not operate it directly.
  For example, if a robot transfer task moves a container from device A to device B, the robot arm and both devices should be required.
* Branches and loops are not supported. If needed, encapsulate them inside larger tasks that span multiple protocol steps.
