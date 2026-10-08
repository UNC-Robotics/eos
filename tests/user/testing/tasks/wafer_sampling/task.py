from eos import Param, task

from testing.devices.analytical_lab.cartesian_robot.device import CartesianRobot


@task("Wafer Sampling")
async def wafer_sampling(
    cartesian_robot: CartesianRobot,
    wafer_spot: tuple[int, int] = Param(
        (0, 0), min=(-10, -10), max=(10, 10), desc="The coordinates of the wafer spot in the wafer station."
    ),
) -> None:
    """Perform wafer sampling with a cartesian robot and pump/valve system."""
