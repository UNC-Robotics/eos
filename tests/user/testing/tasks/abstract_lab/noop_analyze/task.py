from eos import task

from testing.devices.abstract_lab.DT3.device import DT3
from testing.devices.abstract_lab.DT5.device import DT5


@task("Noop Analyze")
async def noop_analyze(analyzer: DT3, processor: DT5) -> None:
    """This task uses an analyzer and a processor and does nothing."""
