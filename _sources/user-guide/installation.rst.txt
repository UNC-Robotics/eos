Installation
============

EOS should be installed on a capable computer in the laboratory.
We recommend a central computer that is easily accessible.

.. note::
    If EOS will be connecting to other computers to run automation, then you must ensure that the computer where EOS
    is installed has bi-directional network access to the other computers.

    We strongly recommend that the laboratory has its own isolated network for security and performance reasons.
    See :doc:`infrastructure setup <infrastructure_setup>` for more information.

EOS also requires a MongoDB database and a MinIO object storage server.
We provide a Docker Compose file that can set up all of these services for you.

1. Install PDM
^^^^^^^^^^^^^^
PDM is used as the project manager for EOS, making it easier to install dependencies and build it.

See the `PDM documentation <https://pdm-project.org/en/latest/>`_ for more information or if you encounter any issues.

.. tab-set::

    .. tab-item:: Linux/Mac

        .. code-block:: shell

            curl -sSL https://pdm-project.org/install-pdm.py | python3 -

    .. tab-item:: Windows

        .. code-block:: shell

            (Invoke-WebRequest -Uri https://pdm-project.org/install-pdm.py -UseBasicParsing).Content | py -

2. Clone the EOS Repository
^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. code-block:: shell

    git clone https://github.com/UNC-Robotics/eos

3. Make a Virtual Environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
We create a virtual environment to isolate the dependencies of EOS from the rest of the system. The virtual environment
is created in a ``env`` directory inside the EOS repository directory. Feel free to use PDM to manage the virtual
environment instead. Other sections of the documentation will assume that you are using a virtual environment located
inside the EOS repository directory.

.. code-block:: shell

    cd eos # Navigate to the cloned repository
    python3 -m venv env
    source env/bin/activate

4. Install Dependencies
^^^^^^^^^^^^^^^^^^^^^^^
Navigate to the cloned repository and run:

.. code-block:: shell

    pdm install
