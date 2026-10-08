from eos import task

from scheduler_benchmark.devices.robot_arm.device import RobotArm
from scheduler_benchmark.resources import ReactionVial


@task("Fetch Reaction Vial")
async def fetch_reaction_vial(robot_arm: RobotArm, vial: ReactionVial) -> None:
    """Fetch an empty reaction vial from storage with the robot arm."""
