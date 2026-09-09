Optimizers
==========
A sequential optimizer proposes task parameters and learns from completed protocol runs.
EOS runs it in a dedicated Ray actor, optionally on another computer selected by ``optimizer_ip``.

.. figure:: ../_static/img/optimize-protocol-loop.png
   :alt: Optimization and protocol run loop
   :align: center

Choose an Optimizer
-------------------
* ``BayesianSequentialOptimizer`` uses BoFire and BoTorch for constrained single-objective
  or multi-objective optimization.
* :doc:`beacon_optimizer` mixes an optimizer with AI suggestions, a journal, and expert insights.
* Implement ``AbstractSequentialOptimizer`` for a standalone algorithm, or follow
  :doc:`custom_beacon` to plug one into Beacon.

Protocol Integration
--------------------
Place ``optimizer.py`` beside ``protocol.yml``. Its factory returns constructor arguments and
an optimizer class. Input and output keys use ``task_name.parameter_name`` so EOS can collect
and route values.

This Bayesian optimizer works with the bundled multiplication protocol:

.. code-block:: python

    from bofire.data_models.acquisition_functions.acquisition_function import qLogNEI
    from bofire.data_models.features.continuous import ContinuousOutput
    from bofire.data_models.features.discrete import DiscreteInput
    from bofire.data_models.objectives.identity import MinimizeObjective

    from eos.optimization.sequential_bayesian_optimizer import BayesianSequentialOptimizer


    def eos_create_campaign_optimizer():
        return {
            "inputs": [
                DiscreteInput(key="mult_1.number", values=list(range(2, 34))),
                DiscreteInput(key="mult_1.factor", values=list(range(2, 18))),
                DiscreteInput(key="mult_2.factor", values=list(range(2, 18))),
            ],
            "outputs": [
                ContinuousOutput(
                    key="score_multiplication.loss",
                    objective=MinimizeObjective(),
                ),
            ],
            "constraints": [],
            "acquisition_function": qLogNEI(),
            "num_initial_samples": 5,
        }, BayesianSequentialOptimizer

The domain contains input features, output objectives, and constraints. The acquisition function
selects later Bayesian samples after initialization. See the
`BoFire documentation <https://experimental-design.github.io/bofire/>`_ for domain and strategy options.

Custom Optimizer Contract
-------------------------
Inherit from ``eos.optimization.abstract_sequential_optimizer.AbstractSequentialOptimizer``
and implement these methods:

.. list-table::
   :header-rows: 1

   * - Method
     - Contract
   * - ``sample(num_protocol_runs=1)``
     - Return a DataFrame with one row per requested run and one column per input.
   * - ``report(inputs_df, outputs_df)``
     - Record measured results. Input and output rows must correspond.
   * - ``get_optimal_solutions()``
     - Return the best observed inputs and outputs, or the non-dominated set for multiple objectives.
   * - ``get_input_names()`` / ``get_output_names()``
     - Return the DataFrame column names.
   * - ``get_num_samples_reported()``
     - Count reported rows, not sampling calls.

Results may arrive in batches or out of order. Track pending samples if the algorithm needs to
avoid duplicates. On resume, EOS creates a new optimizer and replays completed results.

Define classes in ``optimizer.py`` or install them as an importable Python package on the
optimizer worker. EOS loads ``optimizer.py`` by file path without adding its directory to
``sys.path``. Sibling modules need an importable package path.

See :doc:`custom_beacon` for a complete grid-search implementation of this contract.

.. _optimizer-parameter-schema:

Parameter Schema and Runtime Controls
-------------------------------------
Declare ``eos_param_schema()`` on the optimizer class returned by the factory. It is optional
and defaults to an empty list. EOS uses it for submission controls and allowed overrides.

.. code-block:: python

    @classmethod
    def eos_param_schema(cls):
        return [
            {"key": "descending", "type": "checkbox", "default": False, "runtime": True},
        ]

.. list-table::
   :header-rows: 1

   * - Field
     - Meaning
   * - ``key`` / ``type``
     - Required constructor argument name and control type. Types are ``number``, ``text``,
       ``select``, ``checkbox``, and ``json``.
   * - ``label`` / ``description``
     - Optional display name and help text. The label defaults to the key.
   * - ``default``
     - Value displayed when no override is supplied. Keep it consistent with the constructor.
   * - ``min`` / ``max`` / ``step``
     - Numeric control bounds and increment.
   * - ``options``
     - Allowed choices for ``select``.
   * - ``runtime``
     - Whether the parameter can change during a campaign. Defaults to false.

Runtime controls also require ``get_runtime_params()`` and ``set_runtime_params(params)``.
The getter's keys are the runtime API allowlist. Validate values in the setter. UI constraints
are not a substitute for validation in your optimizer.

Beacon merges the inner optimizer's runtime parameters with its own, forwards custom updates,
and persists them for resume. Standalone optimizers can implement ``get_meta()`` and
``restore_meta(meta)`` to persist additional state. The web UI shows AI controls only for Beacon subclasses.
