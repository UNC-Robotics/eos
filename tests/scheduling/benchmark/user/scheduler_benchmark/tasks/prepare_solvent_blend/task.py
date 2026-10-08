from eos import task

from scheduler_benchmark.devices.dispenser.device import Dispenser
from scheduler_benchmark.resources import SolventCartridge


@task("Prepare Solvent Blend")
async def prepare_solvent_blend(dispenser: Dispenser, cartridge: SolventCartridge) -> None:
    """Pre-load a solvent cartridge with a blended solvent."""
