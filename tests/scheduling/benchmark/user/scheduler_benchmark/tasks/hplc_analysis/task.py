from eos import task

from scheduler_benchmark.devices.hplc.device import Hplc


@task("HPLC Analysis")
async def hplc_analysis(hplc: Hplc) -> None:
    """Run the HPLC analytical method."""
