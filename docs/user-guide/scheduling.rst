Scheduling
==========
EOS schedules experiments, meaning it determines *when* and *on which resources* tasks run.
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
- Use **CP-SAT** for globally optimized scheduling (many tasks/experiments, shared resources, priorities, strict sequencing).

The greedy scheduler can achieve higher throughput than CP-SAT in graphs where task durations are highly variable.

.. note::
   CP-SAT is CPU-intensive for large graphs. It benefits significantly from multiple CPU cores.

Task durations
--------------
CP-SAT requires task durations. Each task in an ``experiment.yml`` must provide an expected duration in **seconds**.
If omitted, tasks default to **1 second**.

:bdg-primary:`experiment.yml`

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
--------------
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

Comparion table
---------------
.. list-table::
   :header-rows: 1
   :widths: 28 36 36

   * - Capability
     - Greedy Scheduler
     - CP-SAT Scheduler
   * - Decision scope
     - ✅ Per-task, on demand
     - ✅ Global schedule across experiments
   * - Optimization goal
     - ✅ Start tasks ASAP
     - ✅ Minimize experiment durations
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
   * - Experiment priorities
     - ❌ Only for tie-breaks
     - ✅ Shapes overall completion order
   * - Multi-experiment optimization
     - ❌ Per experiment
     - ✅ Joint scheduling of all experiments
   * - Tuning / parameters
     - ❌ None
     - ✅ Solver knobs (time limit, workers, seed)
   * - Computational complexity
     - Low
     - High
