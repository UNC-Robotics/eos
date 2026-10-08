from eos import task

from scheduler_benchmark.devices.balance.device import Balance
from scheduler_benchmark.devices.robot_arm.device import RobotArm
from scheduler_benchmark.resources import ReactionVial


@task("Weigh Solid Reagent")
async def weigh_solid_reagent(robot_arm: RobotArm, balance: Balance, vial: ReactionVial) -> None:
    """Weigh a solid reagent into the reaction vial on a balance."""
