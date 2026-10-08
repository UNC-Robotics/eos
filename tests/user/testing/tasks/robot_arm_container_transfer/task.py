from eos import Param, task

from testing.devices.analytical_lab.fixed_arm_robot.device import FixedArmRobot


@task("Container Transfer")
async def container_transfer(
    fixed_arm_robot: FixedArmRobot,
    source_location: str = Param(desc="The name of the source location."),
    source_location_area: str = Param(desc="The name of the source location area."),
    target_location: str = Param(desc="The name of the target location."),
    target_location_area: str = Param(desc="The name of the target location area."),
) -> None:
    """Transfer a container from one location area to another using a robot arm."""
