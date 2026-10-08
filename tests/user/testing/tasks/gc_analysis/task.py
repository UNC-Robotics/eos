from pydantic import BaseModel

from eos import Param, task

from testing.devices.analytical_lab.gas_chromatograph.device import GasChromatograph


class GcAnalysisOutputs(BaseModel):
    result_folder_path: str = Param(desc="The path to the folder containing the results of the GC analysis.")


@task("GC Analysis")
async def gc_analysis(
    gas_chromatograph: GasChromatograph,
    injection_volume: int = Param(unit="ul", min=1, max=10, desc="Sample volume injected into the GC."),
    oven_temperature_initial: int = Param(unit="C", min=40, max=100, desc="Initial temperature of the GC oven."),
    oven_temperature_final: int = Param(unit="C", min=150, max=300, desc="Final temperature of the GC oven."),
    temperature_ramp_rate: int = Param(unit="C/min", min=1, max=20, desc="Rate the oven temperature increases."),
    carrier_gas: str = Param(desc="The carrier gas used in the GC analysis, e.g., Helium."),
    flow_rate: int = Param(unit="ml/min", min=1, max=5, desc="The flow rate of the carrier gas."),
) -> GcAnalysisOutputs:
    """Perform gas chromatography (GC) analysis on a sample."""
    return GcAnalysisOutputs(result_folder_path="")
