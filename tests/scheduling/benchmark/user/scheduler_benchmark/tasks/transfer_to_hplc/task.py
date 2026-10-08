from eos import task

from scheduler_benchmark.devices.hplc.device import Hplc
from scheduler_benchmark.devices.robot_arm.device import RobotArm
from scheduler_benchmark.resources import ReactionVial


@task("Transfer To HPLC")
async def transfer_to_hplc(robot_arm: RobotArm, hplc: Hplc, vial: ReactionVial) -> None:
    """Load the filtered sample vial into the HPLC autosampler."""
