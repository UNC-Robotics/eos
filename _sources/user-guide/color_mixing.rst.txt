Color Mixing
============
This example demonstrates how EOS can be used to implement a virtual color mixing experiment.
In this experiment, we mix CMYK ingredient colors to produce a target color.
By employing Bayesian optimization, the goal is to find task input parameters to synthesize a target color with a
secondary objective of minimizing the amount of color ingredients used.
To make it easy to try out, this example uses no physical devices, but instead uses virtual ones.
Color mixing is simulated using real-time fluid simulation running in a web browser.

The example is implemented in an EOS package called **color_lab**, and can be found `here <https://github.com/UNC-Robotics/eos-examples>`_.

Installation
------------
1. Clone the `eos-examples` repository inside the EOS user directory:

.. code-block:: bash

    cd eos/user
    git clone https://github.com/UNC-Robotics/eos-examples eos_examples

2. Install the package's dependencies in the EOS venv:

.. code-block:: bash

   uv pip install -r user/eos_examples/color_lab/pyproject.toml

3. Load the package in EOS:

Edit the ``config.yml`` file to have the following for user_dir, labs, and experiments:

.. code-block:: yaml

  user_dir: ./user
  labs:
    - color_lab
  experiments:
    - color_mixing

Sample Usage
------------
1. ``cd`` into the ``eos`` directory
2. Run ``python3 user/eos_examples/color_lab/device_drivers.py`` to start the fluid simulation and simulated device drivers.
3. Start EOS.
4. Submit tasks, experiments, or campaigns through the REST API.

You can submit a request to run a campaign through the REST API with `curl` as follows:

.. code-block:: bash

    curl -X POST http://localhost:8070/api/campaigns \
         -H "Content-Type: application/json" \
         -d '{
              "name": "color_mixing",
              "experiment_type": "color_mixing",
              "owner": "name",
              "priority": 0,
              "max_experiments": 100,
              "max_concurrent_experiments": 3,
              "optimize": true,
              "optimizer_ip": "127.0.0.1",
              "global_parameters": {
                "score_color": {
                    "target_color": [47, 181, 49]
                }
              }
        }'

.. note::

    Do not minimize the fluid simulation browser windows while the campaign is running as the simulation may pause running.

Package Structure
-----------------
The top-level structure of the ``color_lab`` package is as follows:

.. code-block:: text

    color_lab/
    ├── common/ <-- contains shared code
    ├── devices/ <-- contains the device implementations
    ├── experiments/ <-- contains the color mixing experiment definitions
    ├── tasks/ <-- contains the task definitions
    ├── fluid_simulation/ <-- contains the source code for the fluid simulation web app
    └── device_drivers.py <-- a script for starting the fluid simulation and socket servers for the devices


Devices
-------
The package contains the following device implementations:

* **Color mixer**: Sends commands to the fluid simulation to dispense and mix colors.
* **Color analyzer**: Queries the fluid simulation to get the average fluid color.
* **Robot arm**: Moves sample containers between other devices.
* **Cleaning station**: Cleans sample containers (by erasing their stored metadata).

This is the Python code for the color analyzer device:

:bdg-primary:`device.py`

.. code-block:: python

    from typing import Any

    from eos.resources.entities.resource import Resource
    from eos.devices.base_device import BaseDevice
    from user.eos_examples.color_lab.common.device_client import DeviceClient


    class ColorAnalyzer(BaseDevice):
        async def _initialize(self, init_parameters: dict[str, Any]) -> None:
            port = int(init_parameters["port"])
            self.client = DeviceClient(port)
            self.client.open_connection()

        async def _cleanup(self) -> None:
            self.client.close_connection()

        async def _report(self) -> dict[str, Any]:
            return {}

        def analyze(self, container: Resource) -> tuple[Resource, tuple[int, int, int]]:
            rgb = self.client.send_command("analyze", {})
            return container, rgb

You will notice that there is little code here.
In fact, the device implementation communicates with another process over a socket.
This is a common pattern when integrating devices in the laboratory, as device drivers are usually provided by a 3rd
party, such as the device manufacturer.
So often the device implementation simply uses the existing driver.
In some cases, the device implementation may include a full driver implementation.

The device implementation initializes a client that connects to the device driver over a socket.
The device implements one function called ``analyze``, which accepts a beaker resource and returns the resource and the average
RGB value of the fluid color from the fluid simulation.

The device YAML file for the color analyzer device is:

:bdg-primary:`device.yml`

.. code-block:: yaml

    type: color_analyzer
    desc: Analyzes the RGB value of a color mixture

    init_parameters:
      port: 5002

Tasks
-----
The package contains the following tasks:

* **Retrieve container**: Retrieves a beaker from storage and moves it to a color mixer using the robot arm.
* **Mix colors**: Dispenses and mixes colors using a color mixer (fluid simulation).
* **Move container to analyzer**: Moves the beaker from the color mixer to a color analyzer using the robot arm.
* **Analyze color**: Analyzes the color of the fluid using a color analyzer (fluid simulation).
* **Score color**: Calculates a loss function taking into account how close the mixed color is to the target color and
  how much color ingredients were used.
* **Empty container**: Empties a beaker with the robot arm.
* **Clean container**: Cleans a beaker with the cleaning station.
* **Store container**: Stores a beaker in storage with the robot arm.

This is the Python code for the "Analyze color" task:

:bdg-primary:`task.py`

.. code-block:: python

    from eos.tasks.base_task import BaseTask


    class AnalyzeColor(BaseTask):
        async def _execute(
            self,
            devices: BaseTask.DevicesType,
            parameters: BaseTask.ParametersType,
            resources: BaseTask.ResourcesType,
        ) -> BaseTask.OutputType:
            color_analyzer = devices["color_analyzer"]

            resources["beaker"], rgb = color_analyzer.analyze(resources["beaker"])

            output_parameters = {
                "red": rgb[0],
                "green": rgb[1],
                "blue": rgb[2],
            }

            return output_parameters, resources, None

The task implementation is straightforward. We first get a reference to the color analyzer device.
Then, we call the ``analyze`` function from the color analyzer device we saw earlier. Finally, we construct
and return the dict of output parameters and the resources.

The task YAML file is the following:

:bdg-primary:`task.yml`

.. code-block:: yaml

    type: Analyze Color
    desc: Analyze the color of a solution

    devices:
      color_analyzer:
        type: color_analyzer

    input_resources:
      beaker:
        type: beaker

    output_parameters:
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

Laboratory
----------
The laboratory YAML definition is shown below.

We define the devices we discussed earlier.
Note that we define three color mixers and three color analyzers so the laboratory can support up to three simultaneous color mixing experiments.

We also define the resource types and the actual resources (beakers) with their initial locations.

:bdg-primary:`lab.yml`

.. code-block:: yaml

    name: color_lab
    desc: A laboratory for color analysis and mixing

    devices:
      robot_arm:
        desc: Robotic arm for moving containers
        type: robot_arm
        computer: eos_computer

        init_parameters:
          locations:
            - container_storage
            - color_mixer_1
            - color_mixer_2
            - color_mixer_3
            - color_analyzer_1
            - color_analyzer_2
            - color_analyzer_3
            - cleaning_station
            - emptying_location

      cleaning_station:
        desc: Station for cleaning containers
        type: cleaning_station
        computer: eos_computer

        meta:
          location: cleaning_station

      color_mixer_1:
        desc: Color mixing apparatus for incrementally dispensing and mixing color solutions
        type: color_mixer
        computer: eos_computer

        init_parameters:
          port: 5004

        meta:
          location: color_mixer_1

      color_mixer_2:
        desc: Color mixing apparatus for incrementally dispensing and mixing color solutions
        type: color_mixer
        computer: eos_computer

        init_parameters:
          port: 5006

        meta:
          location: color_mixer_2

      color_mixer_3:
        desc: Color mixing apparatus for incrementally dispensing and mixing color solutions
        type: color_mixer
        computer: eos_computer

        init_parameters:
          port: 5008

        meta:
          location: color_mixer_3

      color_analyzer_1:
        desc: Analyzer for color solutions
        type: color_analyzer
        computer: eos_computer

        init_parameters:
          port: 5003

        meta:
          location: color_analyzer_1

      color_analyzer_2:
        desc: Analyzer for color solutions
        type: color_analyzer
        computer: eos_computer

        init_parameters:
          port: 5005

        meta:
          location: color_analyzer_2

      color_analyzer_3:
        desc: Analyzer for color solutions
        type: color_analyzer
        computer: eos_computer

        init_parameters:
          port: 5007

        meta:
          location: color_analyzer_3


    resource_types:
      beaker:
        meta:
          capacity: 300

    resources:
      c_a:
        type: beaker
        meta:
          location: container_storage
      c_b:
        type: beaker
        meta:
          location: container_storage
      c_c:
        type: beaker
        meta:
          location: container_storage
      c_d:
        type: beaker
        meta:
          location: container_storage
      c_e:
        type: beaker
        meta:
          location: container_storage

Experiment
----------
The color mixing experiment is a linear sequence of the following tasks:

#. **retrieve_container**: Get a beaker from storage and move it to a color mixer.
#. **mix_colors**: Iteratively dispense and mix the colors in the beaker.
#. **move_container_to_analyzer**: Move the beaker from the color mixer to a color analyzer.
#. **analyze_color**: Analyze the color of the solution in the beaker and output the RGB values.
#. **score_color**: Score the color (compute the loss function) based on the RGB values.
#. **empty_container**: Empty the beaker and move it to the cleaning station.
#. **clean_container**: Clean the beaker by rinsing it with distilled water.
#. **store_container**: Store the beaker back in the storage.

The YAML definition of the experiment is shown below:

:bdg-primary:`experiment.yml`

.. code-block:: yaml

    type: color_mixing
    desc: Experiment to find optimal parameters to synthesize a desired color

    labs:
      - color_lab

    tasks:
      - name: retrieve_container
        type: Retrieve Container
        desc: Get a container from storage and move it to the color dispenser
        duration: 5
        devices:
          robot_arm:
            lab_name: color_lab
            name: robot_arm
          color_mixer:
            allocation_type: dynamic
            device_type: color_mixer
            allowed_labs: [color_lab]
        resources:
          beaker:
            allocation_type: dynamic
            resource_type: beaker
        dependencies: []

      - name: mix_colors
        type: Mix Colors
        desc: Mix the colors in the container
        duration: 20
        devices:
          color_mixer: retrieve_container.color_mixer
        resources:
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

      - name: move_container_to_analyzer
        type: Move Container to Analyzer
        desc: Move the container to the color analyzer
        duration: 5
        devices:
          robot_arm:
            lab_name: color_lab
            name: robot_arm
          color_mixer: mix_colors.color_mixer
          color_analyzer:
            allocation_type: dynamic
            device_type: color_analyzer
            allowed_labs: [color_lab]
        resources:
          beaker: mix_colors.beaker
        dependencies: [mix_colors]

      - name: analyze_color
        type: Analyze Color
        desc: Analyze the color of the solution in the container and output the RGB values
        duration: 2
        devices:
          color_analyzer: move_container_to_analyzer.color_analyzer
        resources:
          beaker: move_container_to_analyzer.beaker
        dependencies: [move_container_to_analyzer]

      - name: score_color
        type: Score Color
        desc: Score the color based on the RGB values
        duration: 1
        parameters:
          red: analyze_color.red
          green: analyze_color.green
          blue: analyze_color.blue
          total_color_volume: mix_colors.total_color_volume
          max_total_color_volume: 300.0
          target_color: eos_dynamic
        dependencies: [analyze_color]

      - name: empty_container
        type: Empty Container
        desc: Empty the container and move it to the cleaning station
        duration: 5
        devices:
          robot_arm:
            lab_name: color_lab
            name: robot_arm
          cleaning_station:
            allocation_type: dynamic
            device_type: cleaning_station
            allowed_labs: [color_lab]
        resources:
          beaker: analyze_color.beaker
        parameters:
          emptying_location: emptying_location
        dependencies: [analyze_color]

      - name: clean_container
        type: Clean Container
        desc: Clean the container by rinsing it with distilled water
        duration: 5
        devices:
          cleaning_station: empty_container.cleaning_station
        resources:
          beaker: empty_container.beaker
        parameters:
          duration: 2
        dependencies: [empty_container]

      - name: store_container
        type: Store Container
        desc: Store the container back in the container storage
        duration: 5
        devices:
          robot_arm:
            lab_name: color_lab
            name: robot_arm
        resources:
          beaker: clean_container.beaker
        parameters:
          storage_location: container_storage
        dependencies: [clean_container]

Dynamic Parameters and Optimization
-----------------------------------
Dynamic parameters are specified using the special value ``eos_dynamic`` in the experiment.
For campaigns with optimization (``optimize: true``), EOS uses the experiment's optimizer to propose values for the input dynamic parameters.
Some dynamic parameters may still need to be provided by the user. In this experiment, ``score_color.target_color`` must be provided.
Provide it via ``global_parameters`` or ``experiment_parameters`` in the campaign submission as shown above.

The optimizer used for this experiment is defined in ``optimizer.py`` adjacent to the experiment YAML and uses Bayesian optimization to minimize ``score_color.loss``.

References Between Tasks
------------------------
EOS experiments commonly link tasks together by referencing devices, resources, and parameters from earlier tasks. The color mixing experiment demonstrates each kind of reference.

**Device references**: reuse the same physical device across tasks by referencing a named device handle from a prior task.

Example:

.. code-block:: yaml

    - name: mix_colors
      devices:
        color_mixer: retrieve_container.color_mixer

    - name: analyze_color
      devices:
        color_analyzer: move_container_to_analyzer.color_analyzer

In the first snippet, the mix_colors task uses the exact color_mixer allocated during retrieve_container. In the second, analyze_color uses the color_analyzer allocated during move_container_to_analyzer.

**Resource references**: pass the same physical resource instance (e.g., a beaker) downstream.

Example:

.. code-block:: yaml

    - name: mix_colors
      resources:
        beaker: retrieve_container.beaker

    - name: analyze_color
      resources:
        beaker: move_container_to_analyzer.beaker

The beaker chosen (dynamically) in retrieve_container is reused by mix_colors, then moved by the robot and reused by analyze_color.

**Parameter references**: feed outputs from one task as inputs to another by referencing output parameters.

Example:

.. code-block:: yaml

    - name: score_color
      parameters:
        red: analyze_color.red
        green: analyze_color.green
        blue: analyze_color.blue
        total_color_volume: mix_colors.total_color_volume
        max_total_color_volume: 300.0
        target_color: eos_dynamic

The score_color task consumes the RGB outputs from analyze_color and the total color volume from mix_colors.
