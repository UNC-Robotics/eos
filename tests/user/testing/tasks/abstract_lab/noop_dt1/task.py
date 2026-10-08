from eos import task

from testing.devices.abstract_lab.DT1.device import DT1


@task("Noop DT1")
async def noop_dt1(device_1: DT1) -> None:
    """This task uses a DT1 device and does nothing."""
