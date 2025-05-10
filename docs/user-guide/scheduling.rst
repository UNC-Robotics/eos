Scheduling
==========
When executing experiments, EOS uses scheduling to determine the execution order of tasks. EOS offers two types of
scheduling policies:

#. **Greedy**: tasks are scheduled for execution as soon as their requirements (e.g., precedence and device
   constraints) are met.

#. **CP-SAT**: tasks are scheduled based on not only when their requirements are satisfied but also in a way that
   minimizes the total duration of all submitted experiments. To make this happen, the scheduler needs to know how
   long each task is expected to take.

Choosing a scheduler
--------------------
The desired scheduler can be chosen by modifying the EOS ``config.yml`` file:

:bdg-primary:`config.yml`

.. code-block:: yaml

    # ...

    scheduler:
        type: greedy # or cpsat

The greedy scheduler is lightweight and is the recommended scheduler for simpler experiments where task durations
do not have a lot of variance.

The CP-SAT scheduler should be used for more complex experiments, such as experiments with parallel branches, where
ordering tasks by taking into account their durations can make a big difference in the total duration of the experiment.
CP-SAT is a state-of-the-art constraint programming solver, and thus may require significant computational resources to run,
especially for complex experiment task graphs. CP-SAT greatly benefits from multiprocessing, so the more cores on the
EOS computer, the better.

Task durations
--------------
When using the CP-SAT scheduler, every task in an ``experiment.yml`` file must be assigned an expected duration in seconds.
For compatibility reasons, every task has a default duration of 10 seconds, unless specified otherwise. See below:

:bdg-primary:`experiment.yml`

.. code-block:: yaml

    # ...

    tasks:
        # ...
        - id: analyze_color
            type: Analyze Color
            desc: Determine the RGB value of a solution in a container
            duration: 5
            devices:
              - lab_id: color_lab
                id: color_analyzer
            containers:
              beaker: move_container_to_analyzer.beaker
            dependencies: [move_container_to_analyzer]
        # ...
