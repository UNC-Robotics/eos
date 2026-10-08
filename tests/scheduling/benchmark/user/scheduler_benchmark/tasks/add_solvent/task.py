from eos import task

from scheduler_benchmark.devices.dispenser.device import Dispenser
from scheduler_benchmark.devices.prep_station.device import PrepStation
from scheduler_benchmark.resources import ReactionVial, SolventCartridge


@task("Add Solvent")
async def add_solvent(
    dispenser: Dispenser, prep_station: PrepStation, vial: ReactionVial, cartridge: SolventCartridge
) -> None:
    """Dispense the prepared solvent blend into the reaction vial."""
