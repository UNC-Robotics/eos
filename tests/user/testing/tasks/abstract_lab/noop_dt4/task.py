from eos import task

from testing.devices.abstract_lab.DT4.device import DT4


@task("Noop DT4")
async def noop_dt4(device_1: DT4) -> None:
    """This task uses a DT4 device and does nothing."""
