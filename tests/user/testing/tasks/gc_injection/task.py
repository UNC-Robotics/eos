from eos import Param, task

from testing.devices.analytical_lab.mobile_manipulation_robot.device import MobileManipulationRobot


@task("GC Injection")
async def gc_injection(
    mobile_manipulation_robot: MobileManipulationRobot,
    gc_target_name: str = Param(desc="The name of the GC target."),
) -> None:
    """Use a mobile robot to inject a sample into a GC."""
