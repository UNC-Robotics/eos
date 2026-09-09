Color Mixing
============
This example demonstrates a virtual color mixing protocol in EOS.
CMYK ingredient colors are mixed to produce a target color using Bayesian optimization, with a secondary objective of minimizing ingredient usage.
Color mixing runs in a browser fluid simulation without physical devices.

The example is implemented in an EOS package called **color_lab**, and can be found `here <https://github.com/UNC-Robotics/eos-examples>`_.

Installation
------------
1. Clone the `eos-examples` repository inside the EOS user directory:

.. code-block:: bash

    cd eos/user
    git clone https://github.com/UNC-Robotics/eos-examples eos_examples

2. Return to the EOS repository root and install the package dependencies in its environment:

.. code-block:: bash

   eos pkg install color_lab

3. Load the package in EOS:

Edit the ``config.yml`` file to have the following for user_dir, labs, and protocols:

.. code-block:: yaml

  user_dir: ./user
  labs:
    - color_lab
  protocols:
    - color_mixing

Sample Usage
------------
1. ``cd`` into the ``eos`` directory
2. Run ``python3 user/eos_examples/color_lab/device_drivers.py`` to start the fluid simulation and simulated device drivers. Browser windows will open automatically.

   On dual-GPU systems (e.g., NVIDIA + integrated GPU on Wayland), pass ``--browser chrome --nvidia`` to launch the browser with NVIDIA GPU offload and X11 mode for correct WebGL rendering.
3. Start EOS.
4. Submit tasks, protocols, or campaigns through the REST API.

Use the color campaign request in :doc:`rest_api`, setting ``score_color.target_color`` to the desired RGB value.

.. note::

    Do not minimize the fluid simulation browser windows while the campaign is running as the simulation may pause running.

Package Structure
-----------------
The top-level structure of the ``color_lab`` package is as follows:

.. code-block:: text

    color_lab/
    ├── common/ <-- contains shared code
    ├── devices/ <-- contains the device implementations
    ├── protocols/ <-- contains the color mixing protocol definitions
    ├── labs/ <-- contains the laboratory definition
    ├── tasks/ <-- contains the task definitions
    ├── fluid_simulation/ <-- contains the source code for the fluid simulation web app
    └── device_drivers.py <-- a script for starting the fluid simulation and socket servers for the devices


Devices
-------
The package contains the following device implementations:

* **Color station**: Sends commands to the fluid simulation to dispense and mix colors, and queries it to get the average fluid color.
* **Robot arm**: Moves sample containers between other devices.
* **Cleaning station**: Cleans sample containers (by erasing their stored metadata).

This is the Python code for the color station device:

:bdg-primary:`device.py`

.. code-block:: python

    from typing import Any

    from eos.resources.entities.resource import Resource
    from eos.devices.base_device import BaseDevice
    from user.eos_examples.color_lab.common.device_client import DeviceClient


    class ColorStation(BaseDevice):
        async def _initialize(self, init_parameters: dict[str, Any]) -> None:
            port = int(init_parameters["port"])
            self.client = DeviceClient(port)
            self.client.open_connection()

        async def _cleanup(self) -> None:
            self.client.close_connection()

        async def _report(self) -> dict[str, Any]:
            return {}

        def mix(
            self,
            container: Resource,
            cyan_volume: float,
            cyan_strength: float,
            magenta_volume: float,
            magenta_strength: float,
            yellow_volume: float,
            yellow_strength: float,
            black_volume: float,
            black_strength: float,
            mixing_time: int,
            mixing_speed: int,
        ) -> Resource:
            ...

        def analyze(self, container: Resource) -> tuple[Resource, tuple[int, int, int]]:
            rgb = self.client.send_command("analyze", {})
            return container, rgb

The color station combines mixing and analysis into a single device, ensuring a single allocation connects to one fluid simulation window so the mixed color is the same one analyzed.

The implementation communicates with another process over a socket, a common pattern when device drivers are supplied by a third party. It initializes a client that connects to the driver and exposes a ``mix`` function for dispensing colors and an ``analyze`` function that returns the average RGB value from the fluid simulation.

The device YAML file for the color station device is:

:bdg-primary:`device.yml`

.. code-block:: yaml

    type: color_station
    desc: Color mixing and analysis station backed by a fluid simulation

    init_parameters:
      port: 5003

Tasks
-----
The package contains the following tasks:

* **Retrieve container**: Retrieves a beaker from storage and moves it to a color station using the robot arm.
* **Mix colors**: Dispenses and mixes colors using a color station (fluid simulation).
* **Analyze color**: Analyzes the color of the fluid using a color station (fluid simulation).
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
            color_station = devices["color_station"]

            resources["beaker"], rgb = color_station.analyze(resources["beaker"])

            output_parameters = {
                "red": rgb[0],
                "green": rgb[1],
                "blue": rgb[2],
            }

            return output_parameters, resources, None

The task gets a reference to the color station, calls ``analyze``, then returns the output parameters and resources.

The task YAML file is the following:

:bdg-primary:`task.yml`

.. code-block:: yaml

    type: Analyze Color
    desc: Analyze the color of a solution

    devices:
      color_station:
        type: color_station

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
The laboratory YAML definition is shown below. Three color stations are defined to support up to three simultaneous protocol runs. Resource types and beakers with their initial locations are also declared.

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
            - color_station_1
            - color_station_2
            - color_station_3
            - cleaning_station
            - emptying_location

      cleaning_station:
        desc: Station for cleaning containers
        type: cleaning_station
        computer: eos_computer

        meta:
          location: cleaning_station

      color_station_1:
        desc: Color mixing and analysis station backed by a fluid simulation
        type: color_station
        computer: eos_computer

        init_parameters:
          port: 5003

        meta:
          location: color_station_1

      color_station_2:
        desc: Color mixing and analysis station backed by a fluid simulation
        type: color_station
        computer: eos_computer

        init_parameters:
          port: 5004

        meta:
          location: color_station_2

      color_station_3:
        desc: Color mixing and analysis station backed by a fluid simulation
        type: color_station
        computer: eos_computer

        init_parameters:
          port: 5005

        meta:
          location: color_station_3


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

Protocol
--------
The color mixing protocol is a linear sequence of the following tasks:

#. **retrieve_container**: Get a beaker from storage and move it to a color station.
#. **mix_colors**: Iteratively dispense and mix the colors in the beaker.
#. **analyze_color**: Analyze the color of the solution in the beaker and output the RGB values.
#. **score_color**: Score the color (compute the loss function) based on the RGB values.
#. **empty_container**: Empty the beaker and move it to the cleaning station.
#. **clean_container**: Clean the beaker by rinsing it with distilled water.
#. **store_container**: Store the beaker back in the storage.

The YAML definition of the protocol is shown below:

:bdg-primary:`protocol.yml`

.. code-block:: yaml

    type: color_mixing
    desc: Protocol to find optimal parameters to synthesize a desired color

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
          color_station:
            allocation_type: dynamic
            device_type: color_station
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
          color_station: retrieve_container.color_station
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

      - name: analyze_color
        type: Analyze Color
        desc: Analyze the color of the solution in the container and output the RGB values
        duration: 2
        devices:
          color_station: mix_colors.color_station
        resources:
          beaker: mix_colors.beaker
        dependencies: [mix_colors]

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
Dynamic parameters are specified using the special value ``eos_dynamic`` in the protocol.
For campaigns with optimization (``optimize: true``), EOS uses the protocol's optimizer to propose values for the input dynamic parameters.
Some dynamic parameters may still need to be provided by the user. In this protocol, ``score_color.target_color`` must be provided.
Provide it via ``global_parameters`` or ``protocol_run_parameters`` in the campaign submission as shown above.

The optimizer used for this protocol is defined in ``optimizer.py`` adjacent to the protocol YAML and uses Bayesian optimization to minimize ``score_color.loss``.

The protocol reuses its color station and beaker through :doc:`references`. The score task
consumes the measured RGB values and total color volume. See :doc:`scheduling` for holding
allocations between tasks in concurrent campaigns.
