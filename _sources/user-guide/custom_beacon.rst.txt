Customizing Beacon
==================
Replace Beacon's default Bayesian optimizer by overriding ``_create_optimizer``. Beacon retains
AI sampling, fallback, expert insights, journaling, runtime controls, and metadata persistence.
The inner optimizer implements the :doc:`optimizers` contract.

Integration Rules
-----------------
* Set custom constructor attributes **before** calling ``super().__init__()``. Beacon invokes
  ``_create_optimizer(inputs, outputs, constraints)`` during initialization.
* The inner ``sample`` and ``report`` methods must be synchronous. Beacon runs them in a worker thread.
* Accept every valid measured point in ``report``, including points proposed by AI.
* Handle batch sampling and reports that arrive out of order. Completed results are replayed on resume.
* Keep custom parameter names distinct from Beacon settings. Declare UI fields on the Beacon subclass
  and implement runtime getters and setters on the inner optimizer.

A Complete Grid-Search Example
------------------------------
This example searches the multiplication protocol's discrete inputs and minimizes
``score_multiplication.loss``, computed as ``abs(product - 1024)``. It uses no Bayesian acquisition function.
The grid contains 36 combinations, with a minimum loss of 0. One optimum is ``number=4`` with both factors equal to 16.

The implementation supports discrete inputs, one minimization objective, and no constraints.
It tracks pending and completed points to avoid repeating them. Exhausting the grid raises an
error, so limit a grid-only campaign to at most 36 runs.

Download :download:`the complete example <../_examples/custom_beacon.py>` and save it as
``user/example/protocols/optimize_multiplication/optimizer.py``. Back up the existing file first,
then reload the protocol before submitting a new campaign.

Grid Optimizer
~~~~~~~~~~~~~~
The algorithm records all reported results and returns the best observed rows. It reconstructs
its completed-point set when EOS replays results after a resume.

.. literalinclude:: ../_examples/custom_beacon.py
   :language: python
   :pyobject: GridSearchOptimizer

Beacon Subclass
~~~~~~~~~~~~~~~
``descending`` changes the grid traversal order. Its schema creates a checkbox, and the inner
optimizer's runtime methods let Beacon forward and persist changes.

.. literalinclude:: ../_examples/custom_beacon.py
   :language: python
   :pyobject: GridBeacon

Factory
~~~~~~~
The factory defaults to grid-only sampling so the example runs without an AI provider.
To enable AI, configure a :doc:`provider <beacon_optimizer>` and use probabilities such as
``p_bayesian=0.5`` and ``p_ai=0.5``. Despite its name, ``p_bayesian`` selects the custom grid optimizer.

.. literalinclude:: ../_examples/custom_beacon.py
   :language: python
   :pyobject: eos_create_campaign_optimizer

Run and Tune a Campaign
-----------------------
Load the multiplication lab and protocol, then submit a campaign through the web UI or REST API:

.. code-block:: shell

    curl -X POST http://localhost:8070/api/campaigns \
      -H "Content-Type: application/json" \
      -d '{
        "name": "custom_grid",
        "protocol": "optimize_multiplication",
        "owner": "example",
        "max_protocol_runs": 12,
        "optimize": true,
        "meta": {"optimizer_overrides": {"descending": true}}
      }'

Change traversal order while it runs:

.. code-block:: shell

    curl -X PUT http://localhost:8070/api/campaigns/custom_grid/optimizer/params \
      -H "Content-Type: application/json" \
      -d '{"descending": false}'

For the full parameter schema, see :ref:`optimizer-parameter-schema`.
API requests need a bearer token when :doc:`authentication` is enabled.
