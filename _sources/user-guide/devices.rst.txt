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
Devices live in the ``devices`` directory of an EOS package. Each device has its own subdirectory
(e.g., ``devices/magnetic_mixer``) containing a ``device.py``.

A device is a class that subclasses ``Device`` with a ``type``. The docstring is the device description,
and a nested ``Config`` model declares its initialization parameters:

:bdg-primary:`device.py`

.. code-block:: python

    from typing import Any

    from eos import Device

    from my_package.common.device_client import DeviceClient


    class MagneticMixer(Device, type="magnetic_mixer"):
        """Magnetic mixer for mixing the contents of a container."""

        class Config(Device.Config):
            port: int = 5004

        async def _initialize(self, config: Config) -> None:
            self.client = DeviceClient(config.port)
            self.client.open_connection()

        async def _cleanup(self) -> None:
            self.client.close_connection()

        async def _report(self) -> dict[str, Any]:
            return {"port": self.client.port}

        def mix(self, container: str, mixing_time: int, mixing_speed: int) -> None:
            self.client.send_command("mix", {"container": container, "time": mixing_time, "speed": mixing_speed})

One implementation can back several devices of the same type. A lab sets each device's ``init_parameters``,
which EOS validates against ``Config`` when the lab loads and again when the device starts. Fields without
a default are required.

The lifecycle methods are optional:

* ``_initialize`` opens connections, using the validated ``Config``.
* ``_cleanup`` releases them.
* ``_report`` returns current state.

Public methods such as ``mix`` are what tasks call.

Shared Device Code
~~~~~~~~~~~~~~~~~~
A ``Device`` subclass without a ``type`` is not registered, so it can serve as a base class. Subclasses
inherit its methods and type, and extend its ``Config``:

.. code-block:: python

    class BridgeDevice(Device):
        class Config(Device.Config):
            host: str = "127.0.0.1"
            port: int = 8765

        async def _initialize(self, config: Config) -> None:
            self.bridge = Bridge(config.host, config.port)


    class Hotplate(BridgeDevice, type="hotplate"):
        """Hotplate reached through the bridge."""

        class Config(BridgeDevice.Config):
            station: str

        async def _initialize(self, config: Config) -> None:
            self.station = config.station
            await super()._initialize(config)

Devices on Other Computers
~~~~~~~~~~~~~~~~~~~~~~~~~~
EOS ships device code to the computer running the device, so the package does not need to be installed
there. Third-party libraries it uses must be installed on that computer. Import libraries that only exist
there, such as Windows-only SDKs, inside ``_initialize`` so the orchestrator can still load the device.
