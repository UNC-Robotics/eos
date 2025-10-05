Jinja2 Templating
=================
The YAML files used to define labs, devices, experiments, and tasks support `Jinja2 <https://jinja.palletsprojects.com/en/3.1.x/>`_
templating.
This allows easier authoring of complex YAML files by enabling the use of variables, loops, conditionals,
macros, and more.
Jinja2 templates are evaluated with Python, so some expressions are the same as in Python.

.. note::
    Jinja2 templates are evaluated during loading of the YAML file, not during runtime.

Jinja is useful for defining templates.
For example, an experiment template can be defined with placeholders and variables
that when specified lead to different variations of the experiment.
This is particularly useful for altering the task sequence of an experiment while loading it.

.. note::
    Experiment templating is useful if EOS dynamic parameters and references do not suffice.

Below are some useful Jinja2 features:

Variables
---------
Jinja2 allows setting and reading variables in the YAML file.
In the example below, the variable ``max_volume`` is set to 300 and used to define the capacity of two beakers:

:bdg-primary:`lab.yml`

.. code-block:: yaml+jinja

    {% set max_volume = 300 %}
    ...
    resource_types:
      beaker:
        meta:
          capacity: {{ max_volume }}

    resources:
      {% for name in ["c_a", "c_b"] %}
      {{ name }}:
        type: beaker
      {% endfor %}

Arithmetic
----------
You can perform arithmetic within Jinja2 expressions.
In the example below, the volumes of cyan, magenta, and yellow colorants are calculated based on a total color volume:

:bdg-primary:`task.yml`

.. code-block:: yaml+jinja

    {% set total_color_volume = 100 %}
    ...
    parameters:
      cyan_volume: {{ total_color_volume * 0.6 }}
      magenta_volume: {{ total_color_volume * 0.3 }}
      yellow_volume: {{ total_color_volume * 0.1 }}

Conditionals
------------
You can use if statements to include or exclude content based on conditions.
In the example below, the task "mix_colors" is only included if the variable ``mix_colors`` is set to ``True``:

:bdg-primary:`experiment.yml`

.. code-block:: yaml+jinja

    tasks:
      {% if mix_colors %}
      - name: mix_colors
        type: Mix Colors
        desc: Mix the colors in the container
        # ... rest of the task definition
      {% endif %}

Loops
-----
Jinja2 allows you to use loops to generate repetitive content.
In the example below, a loop is used to generate container IDs with a common prefix and a letter (e.g., `c_a`, `c_b`, `c_c`, etc.):

:bdg-primary:`lab.yml`

.. code-block:: yaml+jinja

    resource_types:
      beaker:
        meta:
          capacity: 300

    resources:
      {% for letter in ['a', 'b', 'c', 'd', 'e', 'f', 'g'] %}
      c_{{ letter }}:
        type: beaker
      {% endfor %}

Macros
------
Jinja2 macros allow you to define reusable blocks of content.
In the example below, the ``create_containers`` macro is used to easily create containers with a prefix and a number
(e.g., `c_0`, `c_1`, `c_2`, etc.):

:bdg-primary:`lab.yml`

.. code-block:: yaml+jinja

    {% macro create_resources(res_type, capacity, id_prefix, count) -%}
    resource_types:
      {{ res_type }}:
        meta:
          capacity: {{ capacity }}
    resources:
      {%- for i in range(count) %}
      {{ id_prefix }}{{ i }}:
        type: {{ res_type }}
      {%- endfor %}
    {%- endmacro %}

    {{ create_resources('beaker', 300, 'c_', 5) }}
