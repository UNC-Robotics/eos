Installation
============
Install EOS on the central laboratory computer. You need Python 3.11+, uv, Node.js and npm
for the web UI, and Docker Compose for PostgreSQL and S3-compatible storage.
See :doc:`infrastructure_setup` before connecting other lab computers.

Install uv and EOS
------------------
.. tab-set::

    .. tab-item:: Linux/macOS

        .. code-block:: shell

            curl -LsSf https://astral.sh/uv/install.sh | sh

    .. tab-item:: Windows

        .. code-block:: powershell

            powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

Clone the repository and install dependencies:

.. code-block:: shell

    git clone https://github.com/UNC-Robotics/eos
    cd eos
    uv sync --all-groups

Activate the virtual environment in every terminal before running EOS commands:

.. tab-set::

    .. tab-item:: Linux/macOS

        .. code-block:: shell

            source .venv/bin/activate

    .. tab-item:: Windows

        .. code-block:: powershell

            .venv\Scripts\Activate.ps1

Configure and Start
-------------------
The setup wizard writes the configuration and can bootstrap Zitadel for :doc:`authentication`.
Then start the infrastructure services and EOS, which initializes the database on its first run:

.. code-block:: shell

    eos setup
    eos services up
    eos start

In another terminal, open the EOS repository and activate the virtual environment
using the command above. Then install the web UI dependencies and start it:

.. code-block:: shell

    cd web_ui
    npm install
    eos start ui

The UI defaults to ``http://localhost:3000``. The example configuration loads
``multiplication_lab`` and ``optimize_multiplication``. Change ``config.yml`` to load your packages.

Manual Configuration
--------------------
If you do not use the wizard, copy and edit the templates:

.. code-block:: shell

    cp .env.example .env
    cp config.example.yml config.yml
    cp web_ui/.env.example web_ui/.env

In ``config.yml``, the ``execution`` section can limit how many tasks run at once (``max_concurrent_tasks``)
and set how long to wait for a campaign optimizer to start (``optimizer_startup_timeout``, in seconds).

``.env`` holds the credentials for the PostgreSQL database and the S3-compatible file store
(SeaweedFS). Both run locally in Docker via ``eos services up``, so no external database or AWS account
is needed. Set ``EOS_POSTGRES_USER``, ``EOS_POSTGRES_PASSWORD``, ``EOS_S3_ACCESS_KEY_ID`` and
``EOS_S3_SECRET_ACCESS_KEY`` to values of your choice before running ``eos services up``, and use the same
values in ``web_ui/.env``.

Then initialize services and start the orchestrator:

.. code-block:: shell

    eos services up
    eos db init
    eos start

Install and start the UI as above. For a Docker UI deployment, copy and edit
``web_ui/.env.docker.example`` as ``web_ui/.env.docker``, then run ``docker compose up -d``
from ``web_ui``.

Update EOS
----------
.. code-block:: shell

    eos update

This pulls ``master``, syncs dependencies, and runs database migrations while preserving
user package code and dependencies. Use ``eos update --help`` for options.
