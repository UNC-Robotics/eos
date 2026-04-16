Scheduling
==========
EOS schedules protocols, meaning it determines *when* and *on which resources* tasks run.
Two scheduling policies are provided:

- **Greedy**: starts tasks as soon as requirements are met (dependencies, devices/resources).
- **CP-SAT**: computes a global schedule that respects requirements and minimizes overall completion time,
  using each task’s expected duration.

Choosing a scheduler
--------------------
Select the scheduler in ``config.yml``:

:bdg-primary:`config.yml`

.. code-block:: yaml

    # ...
    scheduler:
      type: greedy   # or: cpsat

**Guidance**

- Use **Greedy** for immediacy and simplicity (small/medium runs, low contention, "start ASAP" behavior).
- Use **CP-SAT** for globally optimized scheduling (many tasks/protocols, shared resources, priorities, strict sequencing).

The greedy scheduler can achieve higher throughput than CP-SAT in graphs where task durations are highly variable.

.. note::
   CP-SAT is CPU-intensive for large graphs. It benefits significantly from multiple CPU cores.

Task durations
--------------
CP-SAT requires task durations. Each task in a ``protocol.yml`` must provide an expected duration in **seconds**.
If omitted, tasks default to **1 second**.

:bdg-primary:`protocol.yml`

.. code-block:: yaml

    # ...
    tasks:
      - name: analyze_color
        type: Analyze Color
        desc: Determine the RGB value of a solution in a container
        duration: 5 # seconds
        devices:
          color_analyzer:
            lab_name: color_lab
            name: color_analyzer
        resources:
          beaker: beaker_A
        dependencies: [move_container_to_analyzer]

.. tip::
   Provide **realistic** average durations for CP-SAT. Better estimates -> better global schedules (fewer conflicts,
   shorter makespan).

Device and resource allocation
------------------------------
Both schedulers support **specific** and **dynamic** devices and resources for tasks.

**Devices**

- *Specific device* - tasks request specific devices with a lab_name/name identifier.
- *Dynamic device* - tasks request "any device of type X," optionally with constraints (allowed labs/devices).

.. code-block:: yaml

    # Specific device
    devices:
      color_analyzer:
        lab_name: color_lab
        name: color_analyzer

    # Dynamic device (one device is selected)
    devices:
      color_analyzer:
        allocation_type: dynamic
        device_type: color_analyzer
        allowed_labs: [color_lab]

**Resources**

- *Specific resource* - tasks request specific resources by name.
- *Dynamic resource* - tasks request resources by **type** (one resource is selected).

.. code-block:: yaml

    # Specific resources
    resources:
      beaker: beaker_A
      buffer: buffer_01

    # Dynamic resource (one resource is selected)
    resources:
      tips:
        allocation_type: dynamic
        resource_type: p200_tips

**How schedulers choose**

- **Greedy**: load balances between available eligible devices/resources at request time.
- **CP-SAT**: chooses devices/resources as part of a **global schedule** to reduce conflicts and overall time.

Task groups
-----------
For workflows that must run some tasks **back-to-back** without gaps (e.g., a tightly coupled sequence), assign the same
``group`` label to consecutive tasks.

.. code-block:: yaml

    tasks:
      - name: prep_sample
        type: Prep Sample
        duration: 120
        group: sample_run_42

      - name: incubate
        type: Incubate
        duration: 600
        group: sample_run_42
        dependencies: [prep_sample]

      - name: readout
        type: Readout
        duration: 90
        group: sample_run_42
        dependencies: [incubate]

.. note::
   The greedy scheduler does not support task groups.

Device and resource holds
-------------------------
When a task completes, its devices and resources are normally released immediately. In a multi-protocol-run
environment another protocol run could claim those resources before the successor task is scheduled. **Holds**
prevent this by keeping the allocation locked until a successor in the same protocol run picks it up.

Add ``hold: true`` to any device or resource slot to enable holding:

.. code-block:: yaml

    tasks:
      - name: setup
        type: Noop
        devices:
          held_device:
            lab_name: abstract_lab
            name: D2
            hold: true              # retain D2 after setup completes

      - name: process
        dependencies: [setup]
        devices:
          held_device:
            ref: setup.held_device
            hold: true              # keep holding for the next successor

      - name: cleanup
        dependencies: [process]
        devices:
          held_device: setup.held_device  # no hold, released after cleanup

**How holds work**

1. When a task with ``hold: true`` completes and has pending successors, its allocation is marked *held*
   rather than released.
2. Held allocations are **transparent** to successor tasks in the same protocol run: they see the device or
   resource as available.
3. The hold is released when a successor picks it up without setting ``hold: true``, when no pending
   successors remain, or when the protocol run ends.

Holds work with every assignment type: specific devices (``lab_name``/``name``), dynamic devices
(``allocation_type: dynamic``), device references, specific resources, dynamic resources, and
resource references. Use the ``ref:`` object form (instead of the short string form) when you need to
combine a reference with ``hold: true``.

.. code-block:: yaml

    # Dynamic device with hold
    devices:
      analyzer:
        allocation_type: dynamic
        device_type: color_analyzer
        hold: true

    # Dynamic resource with hold
    resources:
      beaker:
        allocation_type: dynamic
        resource_type: beaker
        hold: true

Both schedulers fully support holds.

.. tip::
   See :doc:`references` for details on passing devices and resources between tasks.

Protocol run priorities
-----------------------
Each protocol run has an integer priority (default **0**; higher values = higher importance). Priority is set at
submission time via the REST API or a campaign definition, not in ``protocol.yml``.

- **CP-SAT**: after minimizing overall makespan (primary objective), uses priority as a secondary objective so
  that higher-priority protocol runs get earlier task start times.
- **Greedy**: processes protocol runs in priority order each scheduling cycle, giving higher-priority protocol runs
  first pick of available devices and resources.

CP-SAT parameters
-----------------
The CP-SAT scheduler exposes solver parameters that can be tuned for large or complex problem instances:

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Parameter
     - Default
     - Description
   * - ``max_time_in_seconds``
     - 15.0
     - Maximum solver time per scheduling cycle (seconds).
   * - ``num_search_workers``
     - 4
     - Number of CPU threads used by the solver.

.. note::
   The defaults work well for most workloads. Increase ``max_time_in_seconds`` for very large protocol
   graphs where the solver needs more time to find a good schedule.

Scheduling simulation
---------------------
EOS provides a discrete-event simulator (``eos sim``) for testing scheduler behavior offline without running
actual hardware. It is useful for comparing greedy vs. CP-SAT, estimating throughput, and identifying
bottlenecks.

.. code-block:: bash

    eos sim sim_config.yml --scheduler cpsat --jitter 0.1 --seed 42 --verbose

**CLI options**

- ``--scheduler / -s``: ``greedy`` (default) or ``cpsat``.
- ``--jitter``: fraction of duration variance (e.g., ``0.1`` = ±10 %).
- ``--seed``: random seed for reproducible runs.
- ``--verbose / -v``: print scheduling decisions.
- ``--user-dir / -u``: path to EOS packages directory (default ``./user``).

**Simulation config**

:bdg-primary:`sim_config.yml`

.. code-block:: yaml

    packages:
      - my_package
    protocols:
      - type: my_protocol
        iterations: 10
        max_concurrent: 3

**Output** includes a timeline of task START/DONE events, per-device and per-resource utilization percentages,
parallelism metrics (max and average concurrent tasks), and scheduler overhead statistics.

Comparison table
----------------
.. list-table::
   :header-rows: 1
   :widths: 28 36 36

   * - Capability
     - Greedy Scheduler
     - CP-SAT Scheduler
   * - Decision scope
     - ✅ Per-task, on demand
     - ✅ Global schedule across protocols
   * - Optimization goal
     - ✅ Start tasks ASAP
     - ✅ Minimize protocol run durations
   * - Device/resource holds
     - ✅ Supported
     - ✅ Supported
   * - Task groups
     - ❌ Not supported
     - ✅ Supported
   * - Task durations
     - ❌ Not supported
     - ✅ Supported and required
   * - Dynamic device allocation
     - ✅ First available from eligible pool
     - ✅ Optimized choices to reduce conflicts
   * - Dynamic resource allocation
     - ✅ First available from eligible pool
     - ✅ Optimized choices to reduce conflicts
   * - Protocol run priorities
     - ❌ Only for tie-breaks
     - ✅ Shapes overall completion order
   * - Multi-protocol-run optimization
     - ❌ Per protocol run
     - ✅ Joint scheduling of all protocol runs
   * - Tuning / parameters
     - ❌ None
     - ✅ Solver knobs (time limit, workers, seed)
   * - Computational complexity
     - Low
     - High
