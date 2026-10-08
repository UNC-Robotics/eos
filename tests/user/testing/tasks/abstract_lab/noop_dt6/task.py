from eos import task

from testing.devices.abstract_lab.DT6.device import DT6


@task("Noop DT6")
async def noop_dt6(device_1: DT6) -> None:
    """This task uses a DT6 device and does nothing."""
