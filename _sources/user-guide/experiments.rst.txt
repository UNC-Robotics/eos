Experiments
===========
Experiments are a set of tasks that are executed in a specific order. Experiments are represented as directed
acyclic graphs (DAGs) where nodes are tasks and edges are dependencies between tasks. Tasks part of an experiment can
pass parameters and containers to each other using EOS' reference system. Task parameters may be fully defined, with
values provided for all task parameters or they may be left undefined by denoting them as dynamic parameters. Experiments with
dynamic parameters can be used to run campaigns of experiments, where an optimizer generates the values for the
dynamic parameters across repeated experiments to optimize some objectives.

.. figure:: ../_static/img/experiment-graph.png
   :alt: Example experiment graph
   :align: center

Above is an example of a possible experiment that could be implemented with EOS. There is a series of tasks, each
requiring one or more devices. In addition to the task precedence dependencies with edges shown in the graph, there can
also be dependencies in the form of parameters and containers passed between tasks. For example, the task "Mix Solutions"
may take as input parameters the volumes of the solutions to mix, and these values may be output from the "Dispense Solutions"
task. Tasks can reference input/output parameters and containers from other tasks.

Experiment Implementation
-------------------------
* Experiments are implemented in the `experiments` subdirectory inside an EOS package
* Each experiment has its own subfolder (e.g., experiments/optimize_yield)
* There are two key files per experiment: `experiment.yml` and `optimizer.py` (for running campaigns with optimization)

YAML File (experiment.yml)
~~~~~~~~~~~~~~~~~~~~~~~~~~
Defines the experiment. Specifies the experiment type, labs, container initialization (optional), and tasks

Below is an example experiment YAML file for an experiment to optimize parameters to synthesize a specific color:

:bdg-primary:`experiment.yml`

.. code-block:: yaml

    type: color_mixing
    description: Experiment to find optimal parameters to synthesize a desired color

    labs:
      - color_lab

    tasks:
      - id: retrieve_container
        type: Retrieve Container
        description: Get a random available container from storage and move it to the color dispenser
        devices:
          - lab_id: color_lab
            id: robot_arm
          - lab_id: color_lab
            id: container_storage
        containers:
          c_a: c_a
          c_b: c_b
          c_c: c_c
          c_d: c_d
          c_e: c_e
        parameters:
          target_location: color_dispenser
        dependencies: []

      - id: dispense_colors
        type: Dispense Colors
        description: Dispense a color from the color dispenser into the container
        devices:
          - lab_id: color_lab
            id: color_dispenser
        containers:
          beaker: retrieve_container.beaker
        parameters:
          cyan_volume: eos_dynamic
          magenta_volume: eos_dynamic
          yellow_volume: eos_dynamic
          black_volume: eos_dynamic
        dependencies: [retrieve_container]

      - id: move_container_to_mixer
        type: Move Container
        description: Move the container to the magnetic mixer
        devices:
          - lab_id: color_lab
            id: robot_arm
          - lab_id: color_lab
            id: magnetic_mixer
        containers:
          beaker: dispense_colors.beaker
        parameters:
          target_location: magnetic_mixer
        dependencies: [dispense_colors]

      - id: mix_colors
        type: Magnetic Mixing
        description: Mix the colors in the container
        devices:
          - lab_id: color_lab
            id: magnetic_mixer
        containers:
          beaker: move_container_to_mixer.beaker
        parameters:
          mixing_time: eos_dynamic
          mixing_speed: eos_dynamic
        dependencies: [move_container_to_mixer]

      - id: move_container_to_analyzer
        type: Move Container
        description: Move the container to the color analyzer
        devices:
          - lab_id: color_lab
            id: robot_arm
          - lab_id: color_lab
            id: color_analyzer
        containers:
          beaker: mix_colors.beaker
        parameters:
          target_location: color_analyzer
        dependencies: [mix_colors]

      - id: analyze_color
        type: Analyze Color
        description: Analyze the color of the solution in the container and output the RGB values
        devices:
          - lab_id: color_lab
            id: color_analyzer
        containers:
          beaker: move_container_to_analyzer.beaker
        dependencies: [move_container_to_analyzer]

      - id: score_color
        type: Score Color
        description: Score the color based on the RGB values
        parameters:
          red: analyze_color.red
          green: analyze_color.green
          blue: analyze_color.blue
        dependencies: [analyze_color]

      - id: empty_container
        type: Empty Container
        description: Empty the container and move it to the cleaning station
        devices:
          - lab_id: color_lab
            id: robot_arm
          - lab_id: color_lab
            id: cleaning_station
        containers:
          beaker: analyze_color.beaker
        parameters:
          emptying_location: emptying_location
          target_location: cleaning_station
        dependencies: [analyze_color]

      - id: clean_container
        type: Clean Container
        description: Clean the container by rinsing it with distilled water
        devices:
          - lab_id: color_lab
            id: cleaning_station
        containers:
          beaker: empty_container.beaker
        dependencies: [empty_container]

      - id: store_container
        type: Store Container
        description: Store the container back in the container storage
        devices:
          - lab_id: color_lab
            id: robot_arm
          - lab_id: color_lab
            id: container_storage
        containers:
          beaker: clean_container.beaker
        parameters:
          storage_location: container_storage
        dependencies: [clean_container]

Let's dissect this file:

.. code-block:: yaml

    type: color_mixing
    description: Experiment to find optimal parameters to synthesize a desired color

    labs:
      - color_lab

Every experiment has a type. The type is used to essentially identify the class of experiment. When an experiment is running
then there are instances of the experiment with different IDs. Each experiment also requires one or more labs.

Now let's look at the first task in the experiment:

.. code-block:: yaml

    - id: retrieve_container
      type: Retrieve Container
      description: Get a random available container from storage and move it to the color dispenser
      devices:
        - lab_id: color_lab
          id: robot_arm
        - lab_id: color_lab
          id: container_storage
      containers:
        c_a: c_a
        c_b: c_b
        c_c: c_c
        c_d: c_d
        c_e: c_e
      parameters:
        target_location: color_dispenser
      dependencies: []

The first task is named `retrieve_container` and is of type `Retrieve Container`. This task uses the robot arm to get
a random container from storage. The task requires two devices, the robot arm and the container storage. There are five
containers passed to it, "c_a" through "c_e". There is also a parameter `target_location` that is set to `color_dispenser`.
This task has no dependencies as it is the first task in the experiment and is essentially a container feeder.
There are five containers in storage, and one of them is chosen at random for the experiment. All five containers in our
"color lab" are passed to this task, as any one of them could be chosen.

Let's look at the next task:

.. code-block:: yaml

  - id: dispense_colors
    type: Dispense Colors
    description: Dispense a color from the color dispenser into the container
    devices:
      - lab_id: color_lab
        id: color_dispenser
    containers:
      beaker: retrieve_container.beaker
    parameters:
      cyan_volume: eos_dynamic
      magenta_volume: eos_dynamic
      yellow_volume: eos_dynamic
      black_volume: eos_dynamic
    dependencies: [retrieve_container]

This task takes the container from the `retrieve_container` task and dispenses colors into it. The task has an
input container called "beaker" which references the output container named "beaker" from the `retrieve_container` task.
If we look at the `task.yml` file of the task `Retrieve Container` we would see that a container named "beaker" is
defined in `output_containers`. There are also four parameters, the CMYK volumes to dispense. All these parameters are
set to `eos_dynamic`, which is a special keyword in EOS for defining dynamic parameters, instructing the system that
these parameters must be specified either by the user or an optimizer before an experiment is run.

Optimizer File (optimizer.py)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Contains a function that returns the constructor arguments for and the optimizer class type for an optimizer.

As an example, below is the optimizer file for the color mixing experiment:

:bdg-primary:`optimizer.py`

.. code-block:: python

    from typing import Type, Tuple, Dict

    from bofire.data_models.acquisition_functions.acquisition_function import qNEI
    from bofire.data_models.enum import SamplingMethodEnum
    from bofire.data_models.features.continuous import ContinuousOutput, ContinuousInput
    from bofire.data_models.objectives.identity import MinimizeObjective

    from eos.optimization.sequential_bayesian_optimizer import BayesianSequentialOptimizer
    from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer


    def eos_create_campaign_optimizer() -> Tuple[Dict, Type[AbstractSequentialOptimizer]]:
        constructor_args = {
            "inputs": [
                ContinuousInput(key="dispense_colors.cyan_volume", bounds=(0, 5)),
                ContinuousInput(key="dispense_colors.magenta_volume", bounds=(0, 5)),
                ContinuousInput(key="dispense_colors.yellow_volume", bounds=(0, 5)),
                ContinuousInput(key="dispense_colors.black_volume", bounds=(0, 5)),
                ContinuousInput(key="mix_colors.mixing_time", bounds=(1, 15)),
                ContinuousInput(key="mix_colors.mixing_speed", bounds=(10, 500)),
            ],
            "outputs": [
                ContinuousOutput(key="score_color.loss", objective=MinimizeObjective(w=1.0)),
            ],
            "constraints": [],
            "acquisition_function": qNEI(),
            "num_initial_samples": 50,
            "initial_sampling_method": SamplingMethodEnum.SOBOL,
        }

        return constructor_args, BayesianSequentialOptimizer

The `optimizer.py` file is optional and only required for running experiment campaigns with optimization managed by EOS.
More on optimizers can be found in the Optimizers section of the User Guide.
