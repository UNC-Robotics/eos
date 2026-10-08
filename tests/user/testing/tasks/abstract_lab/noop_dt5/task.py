from eos import task

from testing.devices.abstract_lab.DT5.device import DT5


@task("Noop DT5")
async def noop_dt5(device_1: DT5) -> None:
    """This task uses a DT5 device and does nothing."""
