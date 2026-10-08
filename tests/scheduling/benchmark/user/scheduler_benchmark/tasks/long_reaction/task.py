from eos import task

from scheduler_benchmark.devices.reactor.device import Reactor
from scheduler_benchmark.resources import ReactionVial


@task("Long Reaction")
async def long_reaction(reactor: Reactor, vial: ReactionVial) -> None:
    """Long heated reaction (1 hour) holding the vial in the reactor."""
