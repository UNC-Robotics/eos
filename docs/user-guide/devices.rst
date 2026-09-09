Devices
=======
A device is a persistent process that exposes methods to tasks. It can control physical equipment
or hold virtual state across protocol runs. EOS creates device processes when loading a lab.
For objects that only need exclusive allocation, use :doc:`resources`.

.. figure:: ../_static/img/tasks-devices.png
   :alt: EOS Tasks and Devices
   :align: center

The GC Sampling task uses a gas chromatograph and a robot for sample injection.

Device Implementation
---------------------
* Devices are implemented in the `devices` subdirectory inside an EOS package
* Each device has its own subfolder (e.g., devices/magnetic_mixer)
* There are two key files per device: ``device.yml`` and ``device.py``

YAML File (device.yml)
~~~~~~~~~~~~~~~~~~~~~~
* Specifies the device type, desc, and initialization parameters
* The same implementation can be used for multiple devices of the same type
* Initialization parameters can be overridden in laboratory definition

Example device YAML for a magnetic mixer:

:bdg-primary:`device.yml`

.. code-block:: yaml

    type: magnetic_mixer
    desc: Magnetic mixer for mixing the contents of a container

    init_parameters:
      port: 5004

Python File (device.py)
~~~~~~~~~~~~~~~~~~~~~~~
* Implements device functionality
* All devices implementations must inherit from ``BaseDevice``

Example magnetic mixer implementation:

:bdg-primary:`device.py`

.. code-block:: python

    from typing import Any

    from eos.resources.entities.resource import Resource
    from eos.devices.base_device import BaseDevice
    from user.eos_examples.color_lab.common.device_client import DeviceClient


    class MagneticMixer(BaseDevice):
        async def _initialize(self, init_parameters: dict[str, Any]) -> None:
            port = int(init_parameters["port"])
            self.client = DeviceClient(port)
            self.client.open_connection()

        async def _cleanup(self) -> None:
            self.client.close_connection()

        async def _report(self) -> dict[str, Any]:
            return {}

        def mix(self, container: Resource, mixing_time: int, mixing_speed: int) -> Resource:
            result = self.client.send_command("mix", {"mixing_time": mixing_time, "mixing_speed": mixing_speed})
            if result:
                container.meta["mixing_time"] = mixing_time
                container.meta["mixing_speed"] = mixing_speed

            return container

Required lifecycle methods are ``_initialize`` to open connections, ``_cleanup`` to release them,
and ``_report`` to return current state. Task-facing methods such as ``mix`` perform device actions
and may update resource metadata.
