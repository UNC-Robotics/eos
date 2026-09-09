Multi-Computer Lab Setup
========================

One computer runs the EOS orchestrator and Ray head node. Additional computers join as Ray workers.
See :doc:`infrastructure_setup` for network requirements.

Main EOS Computer
-----------------

1. Start Ray head node:

   .. code-block:: shell

       eos ray head

2. Start EOS orchestrator:

   .. code-block:: shell

       eos start

Worker Computers
----------------

1. Install uv, clone EOS, and activate its environment as described in :doc:`installation`.
   On workers, use the worker installer in place of the full dependency installation:

   .. code-block:: shell

       # Install EOS worker dependencies
       python3 scripts/install_worker.py

       # Or, install worker dependencies + dependencies for running EOS campaign optimizers
       python3 scripts/install_worker.py --optimizer

2. Connect to cluster:

   .. code-block:: shell

       eos ray worker -a <head-node-ip>:6379
