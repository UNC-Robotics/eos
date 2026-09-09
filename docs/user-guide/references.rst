References
==========
Use ``task_name.output_name`` to pass a value or reuse an allocation from an earlier task.
The source task must precede the consuming task in the dependency graph.

Syntax
------
.. code-block:: yaml

    devices:
      station: prepare.station
    resources:
      beaker: prepare.beaker
    parameters:
      volume: prepare.measured_volume
    files:
      raw_data: analyze.chromatogram.csv

Keys on the left are the consuming task's aliases or parameter names. References on the right
identify the upstream task and its output. File names may contain dots.

Example
-------
.. code-block:: yaml

    - name: analyze_color
      type: Analyze Color
      dependencies: [mix_colors]
      devices:
        color_station: mix_colors.color_station
      resources:
        beaker: mix_colors.beaker

    - name: score_color
      type: Score Color
      dependencies: [analyze_color]
      parameters:
        red: analyze_color.red
        green: analyze_color.green
        blue: analyze_color.blue
        total_color_volume: mix_colors.total_color_volume
        max_total_color_volume: 300.0
        target_color: eos_dynamic

The first task reuses the station and beaker selected for mixing. The second consumes the
measured RGB values. See :doc:`color_mixing` for the complete protocol.

A reference identifies an allocation but does not reserve it between tasks. Use
:doc:`scheduling` holds when another protocol run must not claim the device or resource in between.
See :doc:`protocols` for fan-in references after conditional branches.
