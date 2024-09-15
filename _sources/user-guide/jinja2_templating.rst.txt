Jinja2 Templating
=================
The EOS YAML files used to define labs, devices, experiments, and tasks support Jinja2 templating. This allows easier
authoring of complex YAML files by enabling the use of variables, loops, and conditionals. Jinja2 templates are evaluated
with Python, so some of the expressions are the same as in Python.

.. note::
    Jinja2 templates are evaluated during loading of the YAML file, not during runtime.

Below is the "containers" portion of a lab YAML file that uses Jinja2 templating:

:bdg-primary:`lab.yml`

.. code-block:: yaml+jinja

    containers:
      - type: beaker
        location: container_storage
        metadata:
          capacity: 300
        ids:
          {% for letter in ['a', 'b', 'c', 'd', 'e'] %}
          - c_{{ letter }}
          {% endfor %}
