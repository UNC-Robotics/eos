REST API
========
EOS has a REST API to control the orchestrator.
Example functions include:

* Submit tasks, experiments, and campaigns, as well as cancel them
* Load, unload, and reload experiments and laboratories
* Get the status of tasks, experiments, and campaigns
* Download task output files

.. warning::

    Be careful about who accesses the REST API.
    The REST API currently has no authentication.

    Only use it internally in its current state.
    If you need to make it accessible over the web use a VPN and set up a firewall.

    EOS will likely have control over expensive (and potentially dangerous) hardware and unchecked REST API access could
    have severe consequences.


Device RPC
----------
EOS provides an RPC endpoint to call device functions directly through the REST API.

**Endpoint:** ``POST /api/rpc/{lab_id}/{device_id}/{function_name}``

**Usage:**

.. code-block:: bash

    curl -X POST "http://localhost:8070/api/rpc/my_lab/pipette/aspirate" \
         -H "Content-Type: application/json" \
         -d '{"volume": 50, "location": "A1"}'

**Parameters:**

* ``lab_id``: The laboratory ID
* ``device_id``: The device ID within the lab
* ``function_name``: The name of the device function to call
* Request body: JSON object containing function parameters

The endpoint will dynamically call the specified function on the device actor with the provided parameters and return the result.

.. warning::

    Direct device control bypasses EOS validation, resource allocation, and scheduling.

Documentation
-------------
The REST API is documented using `OpenAPI <https://swagger.io/specification/>`_ and can be accessed at:

.. code-block:: bash

    http://localhost:8070/docs

or whatever host and port you have configured for the REST API server.
