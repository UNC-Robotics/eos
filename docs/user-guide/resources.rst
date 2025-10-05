Resources
=========
Resources in EOS represent anything that requires exclusive allocation during task execution but does not need its own long‑running process like a device. They cover labware and shared objects such as beakers, vials, tip racks, pipettes, holders, fixtures, bench slots, fridge locations, etc. If multiple tasks could contend for the same physical thing, model it as a resource.

- Use a device when you need a persistent process with methods (e.g., a mixer, GC, robot).
- Use a resource when you only need exclusive use of something for a task.

Defining resources in laboratories
----------------------------------
Resources are defined per laboratory in ``lab.yml`` using two sections:

- ``resource_types``: declares reusable types and their default metadata (e.g., capacity, geometry).
- ``resources``: declares concrete, globally unique resource instances of a given type.

:bdg-primary:`lab.yml`

.. code-block:: yaml

    name: small_lab
    desc: A small laboratory

    devices:
      magnetic_mixer:
        type: magnetic_mixer
        computer: eos_computer

    resource_types:
      beaker_500:
        meta:
          capacity_ml: 500
      p200_tips:
        meta:
          count: 96
      bench_slot:
        meta:
          footprint: 127x85

    resources:
      BEAKER_A:
        type: beaker_500
        meta:
          location: shelf_1
      BEAKER_B:
        type: beaker_500
      TIPS_RACK_1:
        type: p200_tips
      SLOT_1:
        type: bench_slot

Notes
"""""
- Resource names must be globally unique across all labs; EOS enforces this at load time.
- Instance ``meta`` overrides any defaults from the corresponding ``resource_types`` entry.

Declaring resources in task specifications
------------------------------------------
Tasks declare the resource types they require in ``task.yml``. EOS validates that experiments provide matching resource instances (by name) or a dynamic request for a resource of the required type.

:bdg-primary:`task.yml`

.. code-block:: yaml

    type: Magnetic Mixing
    desc: Mix contents in a beaker

    device_types:
      - magnetic_mixer

    input_resources:
      beaker:
        type: beaker_500

    # Optional: if not specified, output_resources default to input_resources
    # output_resources:
    #   beaker:
    #     type: beaker_500

Assigning resources in experiments
----------------------------------
In an experiment’s tasks, assign either specific resource names or request resources dynamically by type. The scheduler (Greedy or CP‑SAT) resolves dynamic requests to a concrete, non‑conflicting resource.

:bdg-primary:`experiment.yml`

.. code-block:: yaml

    type: dynamic_resource_experiment
    desc: Demonstrate resource assignment
    labs: [small_lab]

    tasks:
      - name: prepare
        type: Magnetic Mixing
        duration: 60
        devices:
          mixer:
            lab_name: small_lab
            name: magnetic_mixer
        # Specific resource by name
        resources:
          beaker: BEAKER_A

      - name: process_batch
        type: Magnetic Mixing
        duration: 120
        # Dynamically allocate a beaker of the required type
        resources:
          beaker:
            allocation_type: dynamic
            resource_type: beaker_500
        dependencies: [prepare]

      - name: analyze
        type: Magnetic Mixing
        duration: 30
        # Reuse the same instance selected for 'process_batch'
        # (when a task outputs a resource, it can be referenced by name)
        resources:
          beaker: process_batch.beaker
        dependencies: [process_batch]

.. tip::
   Dynamic resource requests select a single matching resource instance.

Experiment‑level resource metadata (optional)
---------------------------------------------
You may attach experiment‑specific metadata to resources used in that experiment via the top‑level ``resources`` block. This does not define new resources; it annotates existing resource instances.

:bdg-primary:`experiment.yml`

.. code-block:: yaml

    type: water_purification
    desc: Evaporate sample in a beaker
    labs: [small_lab]

    resources:
      BEAKER_A:
        meta:
          substance: salt_water

    tasks:
      - name: mixing
        type: Magnetic Mixing
        resources:
          beaker: BEAKER_A

Allocation and exclusivity
--------------------------
- EOS allocates resources exclusively to the task that holds them; conflicting tasks wait until resources are free.
- Specific assignments must name an existing resource instance defined in one of the experiment’s labs.
- Dynamic assignments select from the pool of eligible instances by ``resource_type``.
- Allocation is handled automatically by the orchestrator and released when the task (or its request scope) finishes.

When to model as a resource
---------------------------
- Labware: beakers, vials, flasks, tip racks, plates.
- Fixtures/locations: bench or instrument slots, holders, storage positions.
- Tools without stateful control loops: manual pipettes, clamps, lids.

Choose a device instead when the object exposes actions and status via a process (e.g., start/stop/move, sensors, drivers).
