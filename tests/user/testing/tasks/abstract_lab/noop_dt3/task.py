from eos import task

from testing.devices.abstract_lab.DT3.device import DT3


@task("Noop DT3")
async def noop_dt3(device_1: DT3) -> None:
    """This task uses a DT3 device and does nothing."""
