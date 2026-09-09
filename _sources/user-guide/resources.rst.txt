Resources
=========
Resources provide exclusive access to labware, tools, and locations such as beakers, tip racks,
and bench slots. Use a :doc:`device <devices>` when the object needs a persistent process with methods.

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
- Resource names must be globally unique across all labs. EOS enforces this at load time.
- Instance ``meta`` overrides any defaults from the corresponding ``resource_types`` entry.

Declaring resources in task specifications
------------------------------------------
Tasks declare required resource types in ``task.yml``. EOS validates that protocols supply matching resource instances (by name) or a dynamic request for the required type.

:bdg-primary:`task.yml`

.. code-block:: yaml

    type: Magnetic Mixing
    desc: Mix contents in a beaker

    devices:
      mixer:
        type: magnetic_mixer

    input_resources:
      beaker:
        type: beaker_500

    # Optional: if not specified, output_resources default to input_resources
    # output_resources:
    #   beaker:
    #     type: beaker_500

Assigning resources in protocols
----------------------------------
In protocol tasks, assign specific resource names or request resources dynamically by type. The scheduler (Greedy or CP-SAT) resolves dynamic requests to a concrete, non-conflicting instance.

:bdg-primary:`protocol.yml`

.. code-block:: yaml

    type: dynamic_resource_protocol
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
        devices:
          mixer: prepare.mixer
        # Dynamically allocate a beaker of the required type
        resources:
          beaker:
            allocation_type: dynamic
            resource_type: beaker_500
        dependencies: [prepare]

      - name: analyze
        type: Magnetic Mixing
        duration: 30
        devices:
          mixer: process_batch.mixer
        # Reuse the same instance selected for 'process_batch'
        # (when a task outputs a resource, it can be referenced by name)
        resources:
          beaker: process_batch.beaker
        dependencies: [process_batch]

.. tip::
   Dynamic resource requests select a single matching resource instance.

Protocol‑level resource metadata (optional)
--------------------------------------------
You may attach protocol-specific metadata to resources via the top-level ``resources`` block. This annotates existing resource instances. It does not define new ones.

:bdg-primary:`protocol.yml`

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
        devices:
          mixer:
            lab_name: small_lab
            name: magnetic_mixer
        resources:
          beaker: BEAKER_A

Allocation and exclusivity
--------------------------
- EOS allocates resources exclusively to the task that holds them. Conflicting tasks wait until resources are free.
- Specific assignments must name an existing resource instance defined in one of the protocol’s labs.
- Dynamic assignments select from the pool of eligible instances by ``resource_type``.
- Allocation is handled automatically by the orchestrator and released when the task (or its request scope) finishes.
