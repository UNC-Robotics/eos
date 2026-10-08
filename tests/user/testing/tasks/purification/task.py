from typing import Literal

from pydantic import BaseModel

from eos import Param, task

from testing.devices.small_lab.evaporator.device import Evaporator
from testing.resources import Beaker500


class PurificationOutputs(BaseModel):
    water_salinity: float = Param(unit="ppm", desc="The salinity of the purified water.")


@task("Purification")
async def purification(
    evaporator: Evaporator,
    beaker: Beaker500,
    method: Literal["evaporation", "simple_mixing"] = Param("evaporation", desc="The purification method."),
    evaporation_time: int = Param(120, unit="sec", min=60, desc="Duration of evaporation."),
    evaporation_temperature: int = Param(90, unit="celsius", min=30, max=150, desc="Evaporation temperature."),
    evaporation_rotation_speed: int = Param(120, unit="rpm", min=10, max=300, desc="Speed of rotation."),
    evaporation_sparging: bool = Param(True, desc="Whether to use sparging gas during evaporation."),
    evaporation_sparging_flow: int = Param(5, unit="ml/min", min=1, max=10, desc="Flow rate of sparging gas."),
    simple_mixing_time: int = Param(120, unit="sec", min=60, desc="Duration of simple mixing."),
    simple_mixing_rotation_speed: int = Param(120, unit="rpm", min=10, max=300, desc="Speed of rotation."),
) -> PurificationOutputs:
    """Purify a substance from its impurities by evaporation or simple mixing."""
    return PurificationOutputs(water_salinity=0.02)
