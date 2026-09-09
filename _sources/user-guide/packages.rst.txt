Packages
========
Packages contain reusable lab, device, task, and protocol definitions, plus supporting code and data.
A package can serve one lab or share equipment implementations across labs.

.. figure:: ../_static/img/package.png
   :alt: EOS package
   :align: center

Place packages under ``user_dir``, which defaults to ``user`` in the EOS repository.

Below is the directory tree of an example EOS package called "color_lab".
It contains a laboratory called "color_lab", the "color_mixing" protocol, and
various devices and tasks. The package also contains a device client under `common`,
and a README file.

.. figure:: ../_static/img/example-package-tree.png
   :alt: Example package directory tree
   :scale: 50%
   :align: center

Create a Package
----------------
.. code-block:: shell

   eos pkg create my_package

This creates the package directory structure. Remove unused subdirectories as needed.

Add Entities to a Package
-------------------------
You can scaffold new labs, devices, tasks, and protocols inside an existing package with the
``eos pkg add`` subcommands. Each one creates the directory under the correct entity folder and
seeds it with empty starter files.

.. code-block:: shell

   eos pkg add lab my_package my_lab            # creates labs/my_lab/lab.yml
   eos pkg add device my_package my_device      # creates devices/my_device/{device.yml, device.py}
   eos pkg add task my_package my_task          # creates tasks/my_task/{task.yml, task.py}
   eos pkg add protocol my_package my_proto     # creates protocols/my_proto/{protocol.yml, optimizer.py}

Install Package Dependencies
----------------------------
Declare Python dependencies in ``pyproject.toml``. ``eos pkg install`` resolves packages by name,
including nested packages, and installs their dependencies with uv.

.. code-block:: shell

   eos pkg install my_package                  # install deps for one package
   eos pkg install my_package other_package    # install deps for several packages
   eos pkg install --all                       # install deps for every discovered package

Any flag-style arguments (and everything after them) are forwarded verbatim to ``uv pip install``.
Use ``--`` if you need to pass a flag that EOS itself interprets (for example, ``--help``):

.. code-block:: shell

   eos pkg install my_package --upgrade
   eos pkg install my_package --index-url https://my.registry/simple
   eos pkg install my_package -- --help        # show uv's help instead of eos's

Dependencies are installed into the active environment and are shared across every
EOS package, since EOS must import user packages from the same interpreter.

Configuring the User Directory
------------------------------
All ``eos pkg`` commands resolve the user directory in the following order:

1. ``--user-dir`` / ``-u`` flag (explicit override).
2. ``user_dir`` field in the config file pointed at by ``--config`` / ``-c`` (default: ``./config.yml``).
3. Fallback: ``./user``.
