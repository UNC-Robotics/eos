Jinja2 Templating
=================
The YAML files used to define labs, devices, protocols, and tasks support `Jinja2 <https://jinja.palletsprojects.com/en/3.1.x/>`_
templating, enabling variables, loops, conditionals, macros, and more.
Jinja2 templates are evaluated with Python, so some expressions follow Python syntax.

.. note::
    Jinja2 templates are evaluated during loading of the YAML file, not during runtime.

Jinja is useful for defining protocol templates with placeholders and variables that produce different
protocol variations when set, including altering the task sequence.

.. note::
    Protocol templating is useful if EOS dynamic parameters and references do not suffice.

Below are some useful Jinja2 features:

Variables
---------
Jinja2 allows setting and reading variables in the YAML file.
Below, ``max_volume`` is set to 300 and used to define the capacity of two beakers:

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
Below, the volumes of cyan, magenta, and yellow colorants are calculated from a total color volume:

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
Below, the task "mix_colors" is included only if the variable ``mix_colors`` is ``True``:

:bdg-primary:`protocol.yml`

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
Jinja2 supports loops to generate repetitive content.
Below, a loop generates container IDs with a common prefix and a letter (e.g., `c_a`, `c_b`, `c_c`):

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
Jinja2 macros define reusable blocks of content.
Below, the ``create_resources`` macro creates resources with a prefix and a number (e.g., `c_0`, `c_1`, `c_2`):

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
