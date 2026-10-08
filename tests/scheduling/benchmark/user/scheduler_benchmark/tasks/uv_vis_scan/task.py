from eos import task

from scheduler_benchmark.devices.uv_vis.device import UvVis
from scheduler_benchmark.resources import AnalysisCuvette


@task("UV-Vis Scan")
async def uv_vis_scan(uv_vis: UvVis, cuvette: AnalysisCuvette) -> None:
    """Run a UV-Vis absorbance scan on the cuvette."""
