Installation
============

EOS should be installed on a capable computer in the laboratory.
We recommend a central computer that is easily accessible.

.. note::
    If EOS will be connecting to other computers to run automation, then you must ensure that the computer where EOS
    is installed has bi-directional network access to the other computers.

    We strongly recommend that the laboratory has its own isolated network for security and performance reasons.
    See :doc:`infrastructure setup <infrastructure_setup>` for more information.

EOS also requires a MongoDB database, a MinIO object storage server, and (for now) Budibase for the web UI.
We provide a Docker Compose file that can set up all of these services for you.

1. Install PDM
^^^^^^^^^^^^^^
PDM is used as the project manager for EOS, making it easier to install dependencies and build it.

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

3. Install Dependencies
^^^^^^^^^^^^^^^^^^^^^^^
Navigate to the cloned repository and run:

.. code-block:: shell

    pdm install

(Optional) If you wish to contribute to EOS development:

.. code-block:: shell

    pdm install -G dev

(Optional) If you also wish to contribute to the EOS documentation:

.. code-block:: shell

    pdm install -G docs
