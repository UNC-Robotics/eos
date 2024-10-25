Configuration
=============

After installation, you need to configure external services such as MongoDB and MinIO as well as EOS itself.

1. Configure External Services
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
We provide a Docker Compose file that can run the external services. You do not need to install external services
manually, just provide configuration values and Docker Compose will take care of the rest.

Copy the example environment file:

.. code-block:: shell

    cp docker/.env.example docker/.env

Edit `docker/.env` and provide values for all fields.

2. Configure EOS
^^^^^^^^^^^^^^^^
EOS reads parameters from a YAML configuration file.

Copy the example configuration file:

.. code-block:: shell

    cp config.example.yml config.yml

Edit `config.yml`. Ensure that credentials are provided for the MongoDB and MinIO services.

By default, EOS loads the "multiplication_lab" laboratory and the "optimize_multiplication" experiment from an example
EOS package. Feel free to change this.
