from eos import task

from testing.devices.abstract_lab.DT2.device import DT2


@task("Noop DT2")
async def noop_dt2(device_1: DT2) -> None:
    """This task uses a DT2 device and does nothing."""
