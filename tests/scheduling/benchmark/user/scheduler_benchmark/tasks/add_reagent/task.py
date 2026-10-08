from eos import task

from scheduler_benchmark.devices.dispenser.device import Dispenser
from scheduler_benchmark.devices.prep_station.device import PrepStation
from scheduler_benchmark.resources import ReactionVial


@task("Add Reagent")
async def add_reagent(dispenser: Dispenser, prep_station: PrepStation, vial: ReactionVial) -> None:
    """Dispense a liquid reagent into the reaction vial."""
