REST API
========
EOS has a REST API to control the orchestrator.
Example functions include:

* Submit tasks, experiments, and campaigns, as well as cancel them
* Load, unload, and reload experiments and laboratories
* Get the status of tasks, experiments, and campaigns
* Download task output files

.. warning::

    The REST API has no authentication. Only expose it on trusted networks.
    Use a VPN or reverse proxy with auth if remote access is needed.


Submitting Experiments
----------------------
Submit an experiment for execution. All dynamic parameters (``eos_dynamic``) must be provided via ``parameters``.

**Endpoint:** ``POST /api/experiments``

.. code-block:: bash

    curl -X POST http://localhost:8070/api/experiments \
         -H "Content-Type: application/json" \
         -d '{
              "name": "my_experiment_1",
              "type": "color_mixing",
              "owner": "alice",
              "priority": 0,
              "parameters": {
                "mix_colors": {
                    "cyan_volume": 10.0,
                    "cyan_strength": 50.0,
                    "magenta_volume": 5.0,
                    "magenta_strength": 30.0,
                    "yellow_volume": 8.0,
                    "yellow_strength": 40.0,
                    "black_volume": 2.0,
                    "black_strength": 20.0,
                    "mixing_time": 15,
                    "mixing_speed": 150
                },
                "score_color": {
                    "target_color": [47, 181, 49]
                }
              }
        }'


Submitting Campaigns
--------------------
Submit a campaign to run an experiment multiple times, optionally with optimizer-driven parameter selection.

**Endpoint:** ``POST /api/campaigns``

**With optimization** (optimizer proposes parameters each iteration):

.. code-block:: bash

    curl -X POST http://localhost:8070/api/campaigns \
         -H "Content-Type: application/json" \
         -d '{
              "name": "color_optimization",
              "experiment_type": "color_mixing",
              "owner": "alice",
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

**Without optimization** (user provides all parameters):

.. code-block:: bash

    curl -X POST http://localhost:8070/api/campaigns \
         -H "Content-Type: application/json" \
         -d '{
              "name": "color_sweep",
              "experiment_type": "color_mixing",
              "owner": "alice",
              "max_experiments": 3,
              "max_concurrent_experiments": 1,
              "optimize": false,
              "experiment_parameters": [
                {"mix_colors": {"cyan_volume": 5, "cyan_strength": 50, "magenta_volume": 0, "magenta_strength": 0, "yellow_volume": 0, "yellow_strength": 0, "black_volume": 0, "black_strength": 0, "mixing_time": 10, "mixing_speed": 150}, "score_color": {"target_color": [0, 200, 200]}},
                {"mix_colors": {"cyan_volume": 0, "cyan_strength": 0, "magenta_volume": 5, "magenta_strength": 50, "yellow_volume": 0, "yellow_strength": 0, "black_volume": 0, "black_strength": 0, "mixing_time": 10, "mixing_speed": 150}, "score_color": {"target_color": [200, 0, 200]}},
                {"mix_colors": {"cyan_volume": 0, "cyan_strength": 0, "magenta_volume": 0, "magenta_strength": 0, "yellow_volume": 5, "yellow_strength": 50, "black_volume": 0, "black_strength": 0, "mixing_time": 10, "mixing_speed": 150}, "score_color": {"target_color": [200, 200, 0]}}
              ]
        }'

.. note::

    When ``optimize`` is ``false``, ``experiment_parameters`` must have exactly ``max_experiments`` entries.


Submitting On-Demand Tasks
--------------------------
Submit a single task for execution outside of an experiment.

**Endpoint:** ``POST /api/tasks``

.. code-block:: bash

    curl -X POST http://localhost:8070/api/tasks \
         -H "Content-Type: application/json" \
         -d '{
              "name": "test_mix",
              "type": "Mix Colors",
              "devices": {
                "color_station": {
                  "lab_name": "color_lab",
                  "name": "color_station_1"
                }
              },
              "input_parameters": {
                "cyan_volume": 10.0,
                "cyan_strength": 50.0,
                "magenta_volume": 5.0,
                "magenta_strength": 30.0,
                "yellow_volume": 8.0,
                "yellow_strength": 40.0,
                "black_volume": 2.0,
                "black_strength": 20.0,
                "mixing_time": 15,
                "mixing_speed": 150
              }
        }'


Cancelling
----------
Cancel a running experiment or campaign:

.. code-block:: bash

    # Cancel an experiment
    curl -X POST http://localhost:8070/api/experiments/my_experiment_1/cancel

    # Cancel a campaign
    curl -X POST http://localhost:8070/api/campaigns/color_optimization/cancel


Querying Status
---------------
Get the status of experiments and campaigns:

.. code-block:: bash

    # Get experiment details
    curl http://localhost:8070/api/experiments/my_experiment_1

    # Get campaign details
    curl http://localhost:8070/api/campaigns/color_optimization


Device RPC
----------
EOS provides an RPC endpoint to call device functions directly through the REST API.

**Endpoint:** ``POST /api/rpc/{lab_id}/{device_id}/{function_name}``

.. code-block:: bash

    curl -X POST "http://localhost:8070/api/rpc/my_lab/pipette/aspirate" \
         -H "Content-Type: application/json" \
         -d '{"volume": 50, "location": "A1"}'

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