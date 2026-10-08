from eos import task

from scheduler_benchmark.devices.reactor.device import Reactor
from scheduler_benchmark.resources import ReactionVial


@task("Heat And Stir")
async def heat_and_stir(reactor: Reactor, vial: ReactionVial) -> None:
    """Short pre-mix to homogenize the reaction mixture before the long reaction."""
