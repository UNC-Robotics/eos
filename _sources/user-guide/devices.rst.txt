Devices
=======
In EOS, a device is an abstraction for a physical or virtual apparatus used by one or more tasks.
Each device is managed by a dedicated process created when a laboratory definition is loaded.
This process is usually implemented as a server that tasks call functions on.
For example, a "magnetic mixer" device communicates with a physical mixer via serial and exposes functions such as ``start``, ``stop``, ``set_time``, and ``set_speed``.

.. figure:: ../_static/img/tasks-devices.png
   :alt: EOS Tasks and Devices
   :align: center

The figure shows a GC Sampling task that uses two devices: a GC and a mobile manipulation robot for automating sample injection with a syringe.
Both are physical devices with EOS implementations running as persistent processes.

Most often an EOS device represents a physical lab instrument, but it can also represent anything that needs persistent state across protocols, such as an AI module that records inputs. A device is always a persistent process.

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

Every device implementation must define the following functions:

#. **_initialize**

   * Called when device process is created
   * Should set up necessary resources (e.g., serial connections)

#. **_cleanup**

   * Called when the device process is terminated
   * Should clean up any resources created by the device process (e.g., serial connections)

#. **_report**

   * Should return any data needed to determine the state of the device (e.g., status and feedback)

The ``mix`` function is called by a task to mix a container's contents. It:

* Sends a command to the lower-level driver with mixing time and speed
* Updates container metadata with the mixing details
