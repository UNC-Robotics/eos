REST API
========
Use the REST API to submit work, inspect results, manage definitions, and call devices.
The examples use the default server at ``http://localhost:8070``. Interactive endpoint documentation
is available at ``http://localhost:8070/docs``.

When :doc:`authentication` is enabled, add ``-H "Authorization: Bearer $TOKEN"`` to requests.
Otherwise, expose the API only on trusted networks.

Submitting Protocol Runs
------------------------
Submit a protocol run. All dynamic parameters (``eos_dynamic``) must be provided via ``parameters``.

**Endpoint:** ``POST /api/protocols``

.. code-block:: bash

    curl -X POST http://localhost:8070/api/protocols \
         -H "Content-Type: application/json" \
         -d '{
              "name": "my_protocol_run_1",
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
Submit a campaign to run a protocol multiple times, optionally with optimizer-driven parameters.

**Endpoint:** ``POST /api/campaigns``

**With optimization** (optimizer proposes parameters each iteration):

.. code-block:: bash

    curl -X POST http://localhost:8070/api/campaigns \
         -H "Content-Type: application/json" \
         -d '{
              "name": "color_optimization",
              "protocol": "color_mixing",
              "owner": "alice",
              "priority": 0,
              "max_protocol_runs": 100,
              "max_concurrent_protocol_runs": 3,
              "optimize": true,
              "optimizer_ip": "127.0.0.1",
              "global_parameters": {
                "score_color": {
                    "target_color": [47, 181, 49]
                }
              }
        }'

**Without optimization**, provide global parameters, a per-run schedule, or both.
This example uses the bundled multiplication protocol:

.. code-block:: bash

    curl -X POST http://localhost:8070/api/campaigns \
      -H "Content-Type: application/json" \
      -d '{
        "name": "multiplication_sweep",
        "protocol": "optimize_multiplication",
        "max_protocol_runs": 3,
        "optimize": false,
        "global_parameters": {"mult_1": {"factor": 8}, "mult_2": {"factor": 16}},
        "protocol_run_parameters": [
          {"mult_1": {"number": 4}},
          {"mult_1": {"number": 8}},
          {"mult_1": {"number": 16}}
        ]
      }'

If supplied without optimization, the schedule must contain exactly ``max_protocol_runs`` entries.
See :doc:`campaigns` for resume and concurrency settings and :doc:`beacon_optimizer` for runtime tuning.

Submitting On-Demand Tasks
--------------------------
Submit a single task for execution outside a protocol run.

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
Cancel a running protocol run or campaign:

.. code-block:: bash

    # Cancel a protocol run
    curl -X POST http://localhost:8070/api/protocols/my_protocol_run_1/cancel

    # Cancel a campaign
    curl -X POST http://localhost:8070/api/campaigns/color_optimization/cancel

Querying Status
---------------
Get the status of protocols and campaigns:

.. code-block:: bash

    # Get protocol run details
    curl http://localhost:8070/api/protocols/my_protocol_run_1

    # Get campaign details
    curl http://localhost:8070/api/campaigns/color_optimization

Device RPC
----------
EOS provides an RPC endpoint to call device functions directly via the REST API.

**Endpoint:** ``POST /api/rpc/{lab_id}/{device_id}/{function_name}``

.. code-block:: bash

    curl -X POST "http://localhost:8070/api/rpc/my_lab/pipette/aspirate" \
         -H "Content-Type: application/json" \
         -d '{"volume": 50, "location": "A1"}'

* ``lab_id``: The laboratory ID
* ``device_id``: The device ID within the lab
* ``function_name``: The name of the device function to call
* Request body: JSON object containing function parameters

The endpoint calls the specified function on the device actor with the provided parameters and returns the result.

.. warning::

    Direct device control bypasses EOS validation, resource allocation, and scheduling.
