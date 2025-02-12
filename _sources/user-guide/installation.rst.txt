Installation
============

EOS should be installed on a capable computer in the laboratory.
We recommend a central computer that is easily accessible.

.. note::
    If EOS will be connecting to other computers to run automation, then you must ensure that the computer where EOS
    is installed has bi-directional network access to the other computers.

    We strongly recommend that the laboratory has its own isolated network for security and performance reasons.
    See :doc:`infrastructure setup <infrastructure_setup>` for more information.

EOS also requires a PostgreSQL database and a MinIO object storage server.
We provide a Docker Compose file that can set up all of these services for you.

1. Install uv
^^^^^^^^^^^^^^
uv is used as the dependency manager for EOS. It installs dependencies extremely fast.

See the `uv documentation <https://docs.astral.sh/uv/>`_ for more information or if you encounter any issues.

.. tab-set::

    .. tab-item:: Linux/Mac

        .. code-block:: shell

            curl -LsSf https://astral.sh/uv/install.sh | sh

    .. tab-item:: Windows

        .. code-block:: shell

            powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

2. Clone the EOS Repository
^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. code-block:: shell

    git clone https://github.com/UNC-Robotics/eos

3. Make a Virtual Environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
We create a virtual environment to isolate the dependencies of EOS from the rest of the system.

.. code-block:: shell

    cd eos # Navigate to the cloned repository
    uv venv
    source .venv/bin/activate

4. Install Dependencies
^^^^^^^^^^^^^^^^^^^^^^^
Navigate to the cloned repository and run:

.. code-block:: shell

    uv sync
