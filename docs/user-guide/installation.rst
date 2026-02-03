Installation
============

EOS should be installed on a central laboratory computer that is easily accessible.

.. note::
    EOS requires bi-directional network access to any computers used for automation.

    Using an isolated laboratory network for security and performance is strongly recommended.
    See :doc:`infrastructure setup <infrastructure_setup>` for details.

EOS requires PostgreSQL and S3-compatible object storage (SeaweedFS by default) for data and file storage. We provide a
Docker Compose file to set up these services.

1. Install uv
^^^^^^^^^^^^^

uv manages dependencies for EOS.

.. tab-set::

    .. tab-item:: Linux/Mac

        .. code-block:: shell

            curl -LsSf https://astral.sh/uv/install.sh | sh

    .. tab-item:: Windows

        .. code-block:: shell

            powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

2. Install EOS
^^^^^^^^^^^^^^

.. code-block:: shell

    # Clone repository
    git clone https://github.com/UNC-Robotics/eos
    cd eos

    # Create and activate virtual environment
    uv venv
    source .venv/bin/activate

    # Install dependencies
    uv sync

3. Configure EOS
^^^^^^^^^^^^^^^^

.. code-block:: shell

    # Set environment variables
    cp .env.example .env
    # Edit .env file and provide values

    # Configure EOS
    cp config.example.yml config.yml
    # Edit config.yml and provide values

4. Launch External Services
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: shell

    # Start external services (PostgreSQL and SeaweedFS)
    docker compose up -d

5. Start EOS
^^^^^^^^^^^^

.. code-block:: shell

    eos start

By default, EOS loads the "multiplication_lab" laboratory and "optimize_multiplication" experiment from an example
package. You can modify this in the configuration file.
