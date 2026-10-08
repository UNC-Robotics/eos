Scheduling
==========
EOS determines *when* and *on which resources* tasks run, using one of three schedulers:

- **Greedy**: starts tasks as soon as requirements are met (dependencies, devices/resources).
- **Heuristic**: starts tasks as soon as requirements are met, but decides which tasks get contended devices and
  resources first using a plan from a fast simulation-based search.
- **CP-SAT**: computes a global schedule that respects requirements and minimizes overall completion time,
  using each task's expected duration.

Choosing a scheduler
--------------------
Select the scheduler in ``config.yml``:

:bdg-primary:`config.yml`

.. code-block:: yaml

    # ...
    scheduler:
      type: greedy   # or: heuristic, cpsat

**Guidance**

- Use **Greedy** for immediacy and simplicity (small/medium runs, low contention, "start ASAP" behavior).
- Use **Heuristic** when protocol runs contend for shared devices and CP-SAT is too slow. It usually gets close
  to CP-SAT makespans while planning in about a second.
- Use **CP-SAT** for globally optimized scheduling (many tasks/protocols, shared resources, priorities, strict sequencing).

The greedy scheduler can achieve higher throughput than CP-SAT in graphs where task durations are highly variable.

.. note::
   CP-SAT is CPU-intensive for large graphs. It benefits significantly from multiple CPU cores.

Task durations
--------------
CP-SAT and the heuristic scheduler use task durations. Each task in a ``protocol.yml`` must provide an expected duration in **seconds**.
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
All schedulers support specific and dynamic device or resource assignments.
See :doc:`protocols` and :doc:`resources` for assignment syntax, and :doc:`references` for reusing
an earlier task's allocation.

**How schedulers choose**

- **Greedy**: load balances between available eligible devices/resources at request time.
- **Heuristic**: chooses devices/resources like greedy, but in a planned task order.
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
   The greedy and heuristic schedulers do not support task groups.

Device and resource holds
-------------------------
When a task completes, its devices and resources are normally released immediately. In a multi-protocol-run
environment another protocol run could claim those resources before a later task that reuses them is scheduled.
**Holds** prevent this by keeping the allocation locked until the later tasks in the same protocol run have used it.

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

1. When a task with ``hold: true`` completes and a pending later task in the same protocol run uses the same
   device or resource (by reference or by name), its allocation is marked *held* rather than released.
2. A held allocation is available only to those later tasks. Other tasks wait, including tasks of the same
   protocol run that need a device or resource of the same type, so they cannot take a vial that holds a sample.
3. The hold is released once no pending later task uses the device or resource, or when the protocol run ends.

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

All schedulers support holds. If no protocol run can make progress because holds of other protocol runs block
them, EOS logs a scheduling deadlock error that lists the holds.

.. tip::
   See :doc:`references` for details on passing devices and resources between tasks.

Protocol run priorities
-----------------------
Each protocol run has an integer priority (default **0**, with higher values taking priority). Priority is set at
submission time via the REST API or a campaign definition, not in ``protocol.yml``.

- **CP-SAT**: after minimizing overall makespan (primary objective), uses priority as a secondary objective so
  that higher-priority protocol runs get earlier task start times.
- **Greedy**: processes protocol runs in priority order each scheduling cycle, giving higher-priority protocol runs
  first pick of available devices and resources.
- **Heuristic**: like greedy, higher-priority protocol runs always get first pick. The planned order applies within
  the same priority.

Heuristic scheduler
-------------------
When protocol runs register or unregister, the heuristic scheduler simulates the remaining work of all runs under
several dispatch rules (topological order, longest remaining path first, shortest task first) and randomized
variants of the best one, and keeps the order with the shortest simulated makespan. Between replans it dispatches
like greedy, so tasks that finish early or late never invalidate the plan.

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Parameter
     - Default
     - Description
   * - ``time_budget_s``
     - 1.0
     - Maximum planning time per replan (seconds).

.. code-block:: yaml

    scheduler:
      type: heuristic
      parameters:
        time_budget_s: 2.0

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
   * - ``warm_start_budget_s``
     - 1.0
     - Time for the heuristic planner to find a starting schedule for each solve (seconds). 0 disables it.

Each solve starts from the heuristic planner's schedule, and CP-SAT keeps that schedule unless it finds a better
one within its time limit. A large workload therefore never waits on a solve that cannot finish. Protocols with
task groups always use CP-SAT's own schedule, because the planner does not keep groups together.

The schedule is executed as an order: a task starts as soon as its dependencies are done and it is next in the
plan on its devices and resources, without waiting for its planned start time.

.. note::
   The defaults work well for most workloads. Increase ``max_time_in_seconds`` for very large protocol
   graphs where the solver needs more time to find a good schedule.

Scheduling simulation
---------------------
EOS provides a discrete-event simulator (``eos sim``) for testing scheduler behavior offline without running
actual hardware. It is useful for comparing schedulers, estimating throughput, and identifying
bottlenecks.

.. code-block:: bash

    eos sim sim_config.yml --scheduler cpsat --jitter 0.1 --seed 42 --verbose

**CLI options**

- ``--scheduler / -s``: ``greedy`` (default), ``heuristic``, or ``cpsat``.
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
