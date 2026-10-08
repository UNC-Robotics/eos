from eos import task

from scheduler_benchmark.devices.prep_station.device import PrepStation
from scheduler_benchmark.devices.robot_arm.device import RobotArm
from scheduler_benchmark.resources import ReactionVial


@task("Transfer To Prep Station")
async def transfer_to_prep_station(robot_arm: RobotArm, prep_station: PrepStation, vial: ReactionVial) -> None:
    """Move the reaction vial from the balance to a prep station."""
