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
1. Install the package's dependencies in the EOS virtual environment:

   .. code-block:: bash

       pip3 install pymixbox websockets

2. Load the package in EOS:

   a. Place the ``color_lab`` directory in the user directory of your EOS installation.

   b. Edit the ``config.yml`` file to have the following for user_dir, labs, and experiments:

      .. code-block:: yaml

          user_dir: ./user
          labs:
            - color_lab
          experiments:
            - color_mixing_1
            - color_mixing_2
            - color_mixing_3

Sample Usage
------------
1. ``cd`` into the ``eos`` directory
2. Run ``python3 user/color_lab/device_drivers.py`` to start the fluid simulation and simulated device drivers.
3. Follow the :doc:`running guide <running>` to run EOS.
4. Submit tasks, experiments, or campaigns through the user interface or the REST API.

For example, you can submit a request to run a campaign through the REST API with ``curl`` as follows:

.. code-block:: bash

    curl -X POST http://localhost:8000 \
         -H "Content-Type: application/json" \
         -d '{
      "campaign_id": "mix_colors",
      "experiment_type": "color_mixing_1",
      "campaign_execution_parameters": {
        "max_experiments": 150,
        "max_concurrent_experiments": 1,
        "do_optimization": true,
        "optimizer_computer_ip": "127.0.0.1",
        "dynamic_parameters": {},
        "resume": false
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

    from eos.containers.entities.container import Container
    from eos.devices.base_device import BaseDevice
    from user.color_lab.common.device_client import DeviceClient


    class ColorAnalyzerDevice(BaseDevice):
        def _initialize(self, initialization_parameters: dict[str, Any]) -> None:
            port = int(initialization_parameters["port"])
            self.client = DeviceClient(port)
            self.client.open_connection()

        def _cleanup(self) -> None:
            self.client.close_connection()

        def _report(self) -> dict[str, Any]:
            return {}

        def analyze(self, container: Container) -> tuple[Container, tuple[int, int, int]]:
            rgb = self.client.send_command("analyze", {})
            return container, rgb

You will notice that there is little code here.
In fact, the device implementation communicates with another process over a socket.
This is a common pattern when integrating devices in the laboratory, as device drivers are usually provided by a 3rd
party, such as the device manufacturer.
So often the device implementation simply uses the existing driver.
In some cases, the device implementation may include a full driver implementation.

The device implementation initializes a client that connects to the device driver over a socket.
The device implements one function called `analyze`, which accepts a container and returns the container and the average
RGB value of the fluid color from the fluid simulation.
The container isn't actually used here as its state is stored in the fluid simulation, but we indicatively include it as
a parameter.

The device YAML file for the color analyzer device is:

:bdg-primary:`device.yml`

.. code-block:: yaml

    type: color_analyzer
    description: Analyzes the RGB value of a color mixture

    initialization_parameters:
      port: 5002

The main thing to notice is that it accepts an initialization parameter called ``port``, which is used to connect to the
device driver over a socket.

Tasks
-----
The package contains the following tasks:

* **Move container**: Moves a container from one device to another using the robot arm.
* **Retrieve container**: Retrieves a container from storage and moves it to the color mixer using the robot arm.
* **Color mixing**: Dispenses and mixes colors using a color mixer (fluid simulation).
* **Analyze color**: Analyzes the color of the fluid using a color analyzer (fluid simulation).
* **Score color**: Calculates a loss function taking into account how close the mixed color is to the target color and
  how much color ingredients were used.
* **Empty container**: Empties a container with the robot arm.
* **Clean container**: Cleans a container with the cleaning station.
* **Store container**: Stores a container in storage with the robot arm.

This is the Python code the "Analyze color" task:

:bdg-primary:`task.py`

.. code-block:: python

    from eos.tasks.base_task import BaseTask


    class AnalyzeColorTask(BaseTask):
        def _execute(
            self,
            devices: BaseTask.DevicesType,
            parameters: BaseTask.ParametersType,
            containers: BaseTask.ContainersType,
        ) -> BaseTask.OutputType:
            color_analyzer = devices.get_all_by_type("color_analyzer")[0]

            containers["beaker"], rgb = color_analyzer.analyze(containers["beaker"])

            output_parameters = {
                "red": rgb[0],
                "green": rgb[1],
                "blue": rgb[2],
            }

            return output_parameters, containers, None

The task implementation is straightforward. We first get a reference to the color analyzer device (there is only one allocated
to the the task). Then, we call the `analyze` function from the color analyzer device we saw earlier. Finally, we construct
and return the dictionary of output parameters and the containers.

The task YAML file is the following:

:bdg-primary:`task.yml`

.. code-block:: yaml

    type: Analyze Color
    description: Analyze the color of a solution

    device_types:
      - color_analyzer

    input_containers:
      beaker:
        type: beaker

    output_parameters:
      red:
        type: integer
        unit: n/a
        description: The red component of the color
      green:
        type: integer
        unit: n/a
        description: The green component of the color
      blue:
        type: integer
        unit: n/a
        description: The blue component of the color

Laboratory
----------
The laboratory YAML definition is shown below.

We first define locations for every device.
The locations have special meaning for the robot arm device, but they are not used for anything else.
In general, locations in EOS are useful for registering the physical locations of devices and sample
containers in the laboratory.
For example, this is important for a mobile manipulation robot which will have to navigate around the lab to pick up and
drop off containers.

Next, we define the devices we discussed earlier.
Note, however, that we define three color mixers and three color analyzers.
The intention is that the laboratory can support up to three simultaneous color mixing experiments.
Each color mixer + color analyzer pair require a dedicated fluid simulation.

Finally, we define the containers.
We define five beakers with a capacity of 300 mL.

:bdg-primary:`lab.yml`

.. code-block:: yaml

   type: color_lab
   description: A laboratory for color analysis and mixing

    locations:
      color_experiment_benchtop:
        description: Benchtop for color experiments
      container_storage:
        description: Storage unit for containers
      color_mixer_1:
        description: Color mixing apparatus for incrementally dispensing and mixing color solutions
      color_mixer_2:
        description: Color mixing apparatus for incrementally dispensing and mixing color solutions
      color_mixer_3:
        description: Color mixing apparatus for incrementally dispensing and mixing color solutions
      color_analyzer_1:
        description: Analyzer for color solutions
      color_analyzer_2:
        description: Analyzer for color solutions
      color_analyzer_3:
        description: Analyzer for color solutions
      cleaning_station:
        description: Station for cleaning containers

    devices:
      cleaning_station:
        description: Station for cleaning containers
        type: cleaning_station
        location: cleaning_station
        computer: eos_computer

      robot_arm:
        description: Robotic arm for moving containers
        type: robot_arm
        location: color_experiment_benchtop
        computer: eos_computer

        initialization_parameters:
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

      color_mixer_1:
        description: Color mixing apparatus for incrementally dispensing and mixing color solutions
        type: color_mixer
        location: color_mixer_1
        computer: eos_computer

        initialization_parameters:
          port: 5004

      color_mixer_2:
        description: Color mixing apparatus for incrementally dispensing and mixing color solutions
        type: color_mixer
        location: color_mixer_2
        computer: eos_computer

        initialization_parameters:
          port: 5006

      color_mixer_3:
        description: Color mixing apparatus for incrementally dispensing and mixing color solutions
        type: color_mixer
        location: color_mixer_3
        computer: eos_computer

        initialization_parameters:
          port: 5008

      color_analyzer_1:
        description: Analyzer for color solutions
        type: color_analyzer
        location: color_analyzer_1
        computer: eos_computer

        initialization_parameters:
          port: 5003

      color_analyzer_2:
        description: Analyzer for color solutions
        type: color_analyzer
        location: color_analyzer_2
        computer: eos_computer

        initialization_parameters:
          port: 5005

      color_analyzer_3:
        description: Analyzer for color solutions
        type: color_analyzer
        location: color_analyzer_3
        computer: eos_computer

        initialization_parameters:
          port: 5007

    containers:
      - type: beaker
        location: container_storage
        metadata:
          capacity: 300
        ids:
          - c_a
          - c_b
          - c_c
          - c_d
          - c_e

Experiment
----------
The color mixing experiment is a linear sequence of the following tasks:

#. **retrieve_container**: Get a container from storage and move it to the color mixer.
#. **mix_colors**: Iteratively dispense and mix the colors in the container.
#. **move_container_to_analyzer**: Move the container from the color mixer to the color analyzer.
#. **analyze_color**: Analyze the color of the solution in the container and output the RGB values.
#. **score_color**: Score the color (compute the loss function) based on the RGB values.
#. **empty_container**: Empty the container and move it to the cleaning station.
#. **clean_container**: Clean the container by rinsing it with distilled water.
#. **store_container**: Store the container back in the storage.

In this example, we want to be able to run 3 simultaneous color mixing experiments, each using a separate pair of color
mixer and color analyzer devices.
In addition, each experiment uses a dedicated container.
Each of the 3 experiments has a different target color.
Ultimately, we set up 3 campaigns, one for each experiment, and we have 3 optimizers.
To reduce duplication, we define a Jinja2 templated experiment which we then include and modify for each of the three
experiments.

The YAML definition for the template experiment is shown below:

:bdg-primary:`template_experiment.yml`

.. code-block:: yaml

    type: {{ experiment_type }}
    description: Experiment to find optimal parameters to synthesize a desired color

    labs:
      - color_lab

    tasks:
      - id: retrieve_container
        type: Retrieve Container
        description: Get a container from storage and move it to the color dispenser
        devices:
          - lab_id: color_lab
            id: robot_arm
        containers:
          beaker: {{ container }}
        parameters:
          target_location: {{ color_mixer }}
        dependencies: []

      - id: mix_colors
        type: Color Mixing
        description: Iteratively dispense and mix the colors in the container
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

      - id: move_container_to_analyzer
        type: Move Container
        description: Move the container from the color mixer to the color analyzer
        devices:
          - lab_id: color_lab
            id: robot_arm
          - lab_id: color_lab
            id: {{ color_mixer }}
        containers:
          beaker: mix_colors.beaker
        parameters:
          target_location: {{ color_mixer }}
        dependencies: [mix_colors]

      - id: analyze_color
        type: Analyze Color
        description: Analyze the color of the solution in the container and output the RGB values
        devices:
          - lab_id: color_lab
            id: {{ color_analyzer }}
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
          total_color_volume: mix_colors.total_color_volume
          max_total_color_volume: 300.0 # based on container capacity
          target_color: {{ target_color }}
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
        parameters:
          duration: 2
        dependencies: [empty_container]

      - id: store_container
        type: Store Container
        description: Store the container back in the container storage
        devices:
          - lab_id: color_lab
            id: robot_arm
        containers:
          beaker: clean_container.beaker
        parameters:
          storage_location: container_storage
        dependencies: [clean_container]

Below is the YAML definition of the first experiment:

:bdg-primary:`experiment.yml`

.. code-block:: yaml+jinja

    {% set experiment_type = 'color_mixing_1' %}
    {% set container = 'c_a' %}
    {% set color_mixer = 'color_mixer_1' %}
    {% set color_analyzer = 'color_analyzer_1' %}
    {% set target_color = '[53, 29, 64]' %}
    {% include 'color_lab/experiments/color_mixing/template_experiment.yml' %}

We specify the experiment type, the container to use, the color mixer and analyzer to use, and the target color.
