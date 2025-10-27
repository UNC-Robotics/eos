SiLA 2 Integration
==================

EOS provides built-in support for `SiLA 2 <https://sila-standard.com/>`_, enabling easier integration with
SiLA-compliant instruments.

Overview
--------

The SiLA integration allows you to:

* Host SiLA servers inside EOS devices
* Connect to external SiLA servers (manual or with autodiscovery)
* Call SiLA servers from tasks with automatic connection management
* Use LockController for exclusive device access (automatic)

Setup
-----
Install the SiLA 2 Python package and supporting packages:

.. code-block:: bash

    uv sync --group sila2

Hosting SiLA Servers
--------------------

Host SiLA servers inside EOS devices using ``SilaDeviceMixin``:

:bdg-primary:`device.py`

.. code-block:: python

    from eos.devices.base_device import BaseDevice
    from eos.integrations.sila import SilaDeviceMixin
    from your_package.sila import Server as YourSilaServer

    class YourDevice(BaseDevice, SilaDeviceMixin):
        async def _initialize(self, init_parameters: dict[str, Any]) -> None:
            self.sila_add_server(
                name="server",
                server_class=YourSilaServer,
                port=init_parameters.get("sila_port", 0),  # 0 = auto-assign
                insecure=init_parameters.get("sila_insecure", True),
            )
            await self.sila_start_all()

        async def _cleanup(self) -> None:
            await self.sila_stop_all()

        async def _report(self) -> dict[str, Any]:
            return {**self.sila_get_status()}

:bdg-primary:`device.yml`

.. code-block:: yaml

    type: your_device
    desc: Device that hosts a SiLA server

    init_parameters:
      sila_port: 0
      sila_insecure: true

Connecting to External SiLA Servers
-----------------------------------

Manual Connection
~~~~~~~~~~~~~~~~~

Connect to a server at a known address:

.. code-block:: python

    self.sila_add_server_connection(
        name="external",
        address="192.168.1.100",
        port=50051,
        insecure=True,
    )

Autodiscovery
~~~~~~~~~~~~~

Use SiLA autodiscovery to find servers on the network:

.. code-block:: python

    self.sila_add_server_connection(
        name="discovered",
        server_name="YourSilaServer",
        timeout=5.0,
        insecure=True,
    )

Using Servers from Tasks
-------------------------

Connect to SiLA servers using ``SilaClientContext``:

:bdg-primary:`task.py`

.. code-block:: python

    from eos.tasks.base_task import BaseTask
    from eos.integrations.sila import SilaClientContext
    from your_package.sila import Client as YourSilaClient

    class YourTask(BaseTask):
        async def _execute(self, devices, parameters, resources):
            device = devices["your_device"]

            async with SilaClientContext.connect(device, YourSilaClient) as client:
                # Call commands
                response = client.YourFeature.YourCommand(Parameter=value)

                # Access properties
                property_value = client.YourFeature.YourProperty.get()

                return {"result": response.Result}, None, None

For devices with multiple servers, specify the server name:

.. code-block:: python

    async with SilaClientContext.connect(device, Client, "server_name") as client:
        ...

Long-Lived Connections
~~~~~~~~~~~~~~~~~~~~~~

For connections that need to persist beyond a single context, use ``create_client()``:

.. code-block:: python

    # Create client without automatic closing
    client = await SilaClientContext.create_client(device, YourSilaClient)

    # Manually lock if needed
    client.lock(timeout=300)

    # Use the client
    response = client.Feature.Command()

    # Manually unlock and close when done
    client.unlock()
    client.close()


Calling Servers from Device Code
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can also call SiLA servers from within an EOS device:

.. code-block:: python

    from eos.devices.base_device import BaseDevice
    from eos.integrations.sila import SilaDeviceMixin, SilaClientContext
    from your_package.sila import Client as YourSilaClient

    class YourDevice(BaseDevice, SilaDeviceMixin):
        async def _initialize(self, init_parameters: dict[str, Any]) -> None:
            # Connect to external SiLA server
            self.sila_add_server_connection(
                name="external",
                server_name="ExternalServer",
                insecure=True,
            )

            # Call the server during initialization
            async with SilaClientContext.connect(self, YourSilaClient) as client:
                self._initial_value = client.Feature.Property.get()

LockController Support
----------------------

EOS automatically handles LockController when present:

* **Auto-detection**: Checks if server has LockController
* **Auto-locking**: Locks with unique UUID (default 60s)
* **Metadata injection**: Adds lock identifier to all calls
* **Auto-retry**: Waits up to 60s if locked
* **Auto-unlock**: Releases on context exit

Default Behavior
~~~~~~~~~~~~~~~~

.. code-block:: python

    # Automatically locked for 60 seconds
    async with SilaClientContext.connect(device, Client) as client:
        response = client.Feature.Command()

Custom Timeout
~~~~~~~~~~~~~~

.. code-block:: python

    # Lock for 120 seconds
    async with SilaClientContext.connect(device, Client, lock_timeout=120) as client:
        ...

Custom Retry Behavior
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Wait up to 30 seconds (60 retries × 0.5s) for lock
    async with SilaClientContext.connect(
        device, Client,
        lock_timeout=120,
        lock_retry_delay=0.5,
        lock_max_retries=60
    ) as client:
        ...

Disable Auto-Locking
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # No automatic locking
    async with SilaClientContext.connect(device, Client, lock_timeout=None) as client:
        ...

Manual Lock Control
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    async with SilaClientContext.connect(device, Client, lock_timeout=None) as client:
        client.lock(timeout=90)  # Lock with auto-generated UUID
        response = client.Feature.Command()
        client.unlock()