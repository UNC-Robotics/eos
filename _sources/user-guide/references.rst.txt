References
==========
References connect tasks in an EOS experiment. They let downstream tasks reuse:
- Devices allocated upstream (device references)

- Physical items used upstream (resource references)

- Output values produced upstream (parameter references)

You write references directly under devices, resources, or parameters in each task’s YAML.


Quick syntax
------------
- Device reference (reuse an allocated device):

  devices:
    <alias>: <upstream_task>.<alias>

- Resource reference (pass the same physical item):

  resources:
    <alias>: <upstream_task>.<alias>

- Parameter reference (consume an output value):

  parameters:
    <param_name>: <upstream_task>.<output_name>


Minimal example
---------------
.. code-block:: yaml

  - name: retrieve_container
    devices:
      robot_arm:
        lab_name: color_lab
        name: robot_arm
      color_mixer:
        allocation_type: dynamic
        device_type: color_mixer
        allowed_labs: [color_lab]
    resources:
      beaker:
        allocation_type: dynamic
        resource_type: beaker
    dependencies: []

  - name: mix_colors
    devices:
      color_mixer: retrieve_container.color_mixer          # device reference
    resources:
      beaker: retrieve_container.beaker                    # resource reference
    parameters:
      cyan_volume: eos_dynamic
      mixing_time: eos_dynamic
    dependencies: [retrieve_container]

  - name: analyze_color
    devices:
      color_analyzer:
        allocation_type: dynamic
        device_type: color_analyzer
        allowed_labs: [color_lab]
    resources:
      beaker: mix_colors.beaker                            # keep same beaker
    dependencies: [mix_colors]

  - name: score_color
    parameters:
      red: analyze_color.red                               # output parameter references
      green: analyze_color.green
      blue: analyze_color.blue
      total_color_volume: mix_colors.total_color_volume
      max_total_color_volume: 300.0
      target_color: eos_dynamic
    dependencies: [analyze_color]
