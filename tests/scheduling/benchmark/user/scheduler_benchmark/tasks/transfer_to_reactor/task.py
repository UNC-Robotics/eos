from eos import task

from scheduler_benchmark.devices.reactor.device import Reactor
from scheduler_benchmark.devices.robot_arm.device import RobotArm
from scheduler_benchmark.resources import ReactionVial


@task("Transfer To Reactor")
async def transfer_to_reactor(robot_arm: RobotArm, reactor: Reactor, vial: ReactionVial) -> None:
    """Move the loaded vial to a heated reactor position."""
