Multi-Computer Lab Setup
========================

EOS can orchestrate experiments across multiple computers, using Ray for distributed communication.
One main computer runs the EOS orchestrator as the head node, while additional computers join as worker nodes.

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

1. Install dependencies:

   .. code-block:: shell

       # Install uv
       curl -LsSf https://astral.sh/uv/install.sh | sh

       # Clone EOS repository
       git clone https://github.com/UNC-Robotics/eos
       cd eos

       # Create and activate virtual environment
       uv venv
       source .venv/bin/activate

       # Install EOS worker dependencies
       python3 scripts/install_worker.py

       # Or, install worker dependencies + dependencies for running EOS campaign optimizers
       python3 scripts/install_worker.py --optimizer

2. Connect to cluster:

   .. code-block:: shell

       eos ray worker -a <head-node-ip>:6379
