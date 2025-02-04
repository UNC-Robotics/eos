REST API
========
EOS has a REST API to control the orchestrator.
Example functions include:

* Submit tasks, experiments, and campaigns
* Cancel tasks, experiments, and campaigns
* Load, unload, and reload experiments and laboratories
* Get the status of tasks, experiments, and campaigns
* Download task output files

.. warning::

    Be very careful to who accesses REST API.
    The REST API currently has no authentication.

    Only use it internally in its current state.
    If you need to make it accessible over the web use a VPN and set up a firewall.

.. warning::

    EOS will likely have control over expensive (and potentially dangerous) hardware and unchecked REST API access could
    have severe consequences.

Documentation
-------------
The REST API is documented using `OpenAPI <https://swagger.io/specification/>`_ and can be accessed at:

.. code-block:: bash

    http://localhost:8000/docs

or whatever host and port you have configured for the REST API server.
