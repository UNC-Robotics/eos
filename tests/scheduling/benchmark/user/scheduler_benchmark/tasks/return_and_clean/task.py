from eos import task

from scheduler_benchmark.devices.robot_arm.device import RobotArm
from scheduler_benchmark.devices.wash_station.device import WashStation


@task("Return And Clean")
async def return_and_clean(robot_arm: RobotArm, wash_station: WashStation) -> None:
    """Return the empty vial to the wash station for cleaning."""
