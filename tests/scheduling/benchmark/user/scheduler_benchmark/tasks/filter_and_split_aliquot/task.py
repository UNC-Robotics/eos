from eos import task

from scheduler_benchmark.devices.dispenser.device import Dispenser
from scheduler_benchmark.devices.workup_station.device import WorkupStation
from scheduler_benchmark.resources import AnalysisCuvette, FilterCartridge, ReactionVial


@task("Filter And Split Aliquot")
async def filter_and_split_aliquot(
    workup_station: WorkupStation,
    dispenser: Dispenser,
    vial: ReactionVial,
    filter: FilterCartridge,  # noqa: A002 (the protocols name this input 'filter')
    cuvette: AnalysisCuvette,
) -> None:
    """Filter the reaction mixture and split an aliquot into a UV-Vis cuvette."""
