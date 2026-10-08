from eos import task

from scheduler_benchmark.devices.robot_arm.device import RobotArm
from scheduler_benchmark.devices.uv_vis.device import UvVis
from scheduler_benchmark.resources import AnalysisCuvette


@task("Transfer To UV-Vis")
async def transfer_to_uv_vis(robot_arm: RobotArm, uv_vis: UvVis, cuvette: AnalysisCuvette) -> None:
    """Move the UV-Vis cuvette into the spectrometer."""
