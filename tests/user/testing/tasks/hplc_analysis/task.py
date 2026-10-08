from typing import Literal

from pydantic import BaseModel

from eos import Param, task

from testing.devices.analytical_lab.high_performance_liquid_chromatograph.device import (
    HighPerformanceLiquidChromatograph,
)
from testing.resources import Vial


class HplcAnalysisOutputs(BaseModel):
    peak_table_file_path: str = Param(desc="Path to the output file summarizing the detected peaks.")
    chromatogram_file_path: str = Param(desc="Path to the output file of chromatogram data.")


@task("HPLC Analysis")
async def hplc_analysis(
    high_performance_liquid_chromatograph: HighPerformanceLiquidChromatograph,
    vial: Vial,
    column: Literal["C18", "C8", "HILIC"] = Param("C18", desc="The type of HPLC column used for separation."),
    mobile_phase_a: str = Param("water", desc="The aqueous mobile phase component."),
    mobile_phase_b: str = Param("acetonitrile", desc="The organic mobile phase component."),
    gradient: str = Param(
        "0 min: 5%B, 10 min: 95%B, 12 min: 95%B, 13 min: 5%B, 15 min: 5%B",
        desc="The gradient elution profile.",
    ),
    flow_rate: float = Param(1.0, unit="ml/min", min=0.1, max=2.0, desc="The mobile phase flow rate."),
    injection_volume: int = Param(10, unit="uL", min=1, max=100, desc="The injected sample volume."),
    detection_wavelength: int = Param(254, unit="nm", min=190, max=800, desc="The detector wavelength."),
) -> HplcAnalysisOutputs:
    """Separate, identify, and quantify the chemical components of a sample with HPLC."""
    return HplcAnalysisOutputs(peak_table_file_path="", chromatogram_file_path="")
