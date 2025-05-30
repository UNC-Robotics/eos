Experiments
===========
Experiments are a set of tasks that are executed in a specific order.
Experiments are represented as directed acyclic graphs (DAGs) where nodes are tasks and edges are dependencies between tasks.
Tasks part of an experiment can pass parameters and containers to each other using EOS' reference system.
Task parameters may be fully defined, with values provided for all task parameters or they may be left undefined by
denoting them as dynamic parameters.
Experiments with dynamic parameters can be used to run campaigns of experiments, where an optimizer generates the values
for the dynamic parameters across repeated experiments to optimize some objectives.

.. figure:: ../_static/img/experiment-graph.png
   :alt: Example experiment graph
   :align: center

Above is an example of a possible experiment that could be implemented with EOS.
There is a series of tasks, each requiring one or more devices.
In addition to the task precedence dependencies with edges shown in the graph, there can also be dependencies in the
form of parameters and containers passed between tasks.
For example, the task "Mix Solutions" may take as input parameters the volumes of the solutions to mix, and these values
may be output from the "Dispense Solutions" task.
Tasks can reference input/output parameters and containers from other tasks.

Experiment Implementation
-------------------------
* Experiments are implemented in the `experiments` subdirectory inside an EOS package
* Each experiment has its own subfolder (e.g., experiments/optimize_yield)
* There are two key files per experiment: ``experiment.yml`` and ``optimizer.py`` (for running campaigns with optimization)

YAML File (experiment.yml)
~~~~~~~~~~~~~~~~~~~~~~~~~~
Defines the experiment.
Specifies the experiment type, labs, container initialization (optional), and tasks

Below is an example experiment YAML file for an experiment to optimize parameters to synthesize a specific color:

:bdg-primary:`experiment.yml`

.. code-block:: yaml

    type: color_mixing
    desc: Experiment to find optimal parameters to synthesize a desired color

    labs:
      - color_lab

    tasks:
      - id: retrieve_container
        type: Retrieve Container
        desc: Get a container from storage and move it to the color dispenser
        devices:
          - lab_id: color_lab
            id: robot_arm
        containers:
          beaker: c_a
        parameters:
          target_location: color_mixer_1
        dependencies: []

      - id: mix_colors
        type: Mix Colors
        desc: Mix the colors in the container
        devices:
          - lab_id: color_lab
            id: color_mixer_1
        containers:
          beaker: retrieve_container.beaker
        parameters:
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
        dependencies: [retrieve_container]

      - id: move_container_to_analyzer
        type: Move Container
        desc: Move the container to the color analyzer
        devices:
          - lab_id: color_lab
            id: robot_arm
          - lab_id: color_lab
            id: color_mixer_1
        containers:
          beaker: mix_colors.beaker
        parameters:
          target_location: color_mixer_1
        dependencies: [mix_colors]

      - id: analyze_color
        type: Analyze Color
        desc: Analyze the color of the solution in the container and output the RGB values
        devices:
          - lab_id: color_lab
            id: color_analyzer_1
        containers:
          beaker: move_container_to_analyzer.beaker
        dependencies: [move_container_to_analyzer]

      - id: score_color
        type: Score Color
        desc: Score the color based on the RGB values
        parameters:
          red: analyze_color.red
          green: analyze_color.green
          blue: analyze_color.blue
          total_color_volume: mix_colors.total_color_volume
          max_total_color_volume: 300.0
          target_color: [53, 29, 64]
        dependencies: [analyze_color]

      - id: empty_container
        type: Empty Container
        desc: Empty the container and move it to the cleaning station
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
        desc: Clean the container by rinsing it with distilled water
        devices:
          - lab_id: color_lab
            id: cleaning_station
        containers:
          beaker: empty_container.beaker
        parameters:
          duration: 2
        dependencies: [empty_container]

      - id: store_container
        type: Store Container
        desc: Store the container back in the container storage
        devices:
          - lab_id: color_lab
            id: robot_arm
        containers:
          beaker: clean_container.beaker
        parameters:
          storage_location: container_storage
        dependencies: [clean_container]

Let's dissect this file:

.. code-block:: yaml

    type: color_mixing
    desc: Experiment to find optimal parameters to synthesize a desired color

    labs:
      - color_lab

Every experiment has a type.
The type is used to identify the class of experiment.
When an experiment is running then there are instances of the experiment with different IDs.
Each experiment also requires one or more labs.

Now let's look at the first task in the experiment:

.. code-block:: yaml

    - id: retrieve_container
      type: Retrieve Container
      desc: Get a container from storage and move it to the color dispenser
      devices:
        - lab_id: color_lab
          id: robot_arm
      containers:
        beaker: c_a
      parameters:
        target_location: color_mixer_1
      dependencies: []

The first task is named ``retrieve_container`` and is of type `Retrieve Container`.
This task uses the robot arm to get a container from storage.
The task requires the robot arm device.
There is a parameter ``target_location`` that is set to ``color_mixer_1``, denoting where to move the container
after retrieving it.
This task has no dependencies as it is the first task in the experiment.

Let's look at the next task:

.. code-block:: yaml

    - id: mix_colors
      type: Mix Colors
      desc: Mix the colors in the container
      devices:
        - lab_id: color_lab
          id: {{ color_mixer }}
      containers:
        beaker: retrieve_container.beaker
      parameters:
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
      dependencies: [retrieve_container]

This task takes the container from the ``retrieve_container`` task, dispenses colors, and mixes them.
The task has an input container called "beaker" which references the output container named "beaker" from the
``retrieve_container`` task.
If we look at the ``task.yml`` file of the task `Retrieve Container` we would see that a container named "beaker" is
defined in ``output_containers``.
There are also parameters for CMYK volumes and strengths, mixing time, and mixing speed.
All these parameters are set to ``eos_dynamic``, which is a special keyword in EOS for defining dynamic parameters,
instructing the system that these parameters must be specified either by the user or an optimizer before an experiment
can be executed.

Optimizer File (optimizer.py)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Contains a function that returns the constructor arguments for and the optimizer class type for an optimizer.

As an example, below is the optimizer file for the color mixing experiment:

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
            "num_initial_samples": 50,
            "initial_sampling_method": SamplingMethodEnum.SOBOL,
        }

        return constructor_args, BayesianSequentialOptimizer

The ``optimizer.py`` file is optional and only required for running experiment campaigns with optimization managed by EOS.
