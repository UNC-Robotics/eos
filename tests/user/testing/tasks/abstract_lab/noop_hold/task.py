from eos import task

from testing.devices.abstract_lab.DT1.device import DT1
from testing.devices.abstract_lab.DT2.device import DT2


@task("Noop Hold")
async def noop_hold(held_device: DT2, shared_device: DT1 | None = None) -> None:
    """This task uses a held DT2 device, and optionally a shared DT1 device, and does nothing."""
