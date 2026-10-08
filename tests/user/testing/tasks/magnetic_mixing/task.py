from pydantic import BaseModel

from eos import Param, task

from testing.devices.small_lab.magnetic_mixer.device import MagneticMixer
from testing.resources import Beaker500


class MagneticMixingOutputs(BaseModel):
    mixing_time: int = Param(unit="sec", desc="The total time the substances were mixed.")


@task("Magnetic Mixing")
async def magnetic_mixing(
    magnetic_mixer: MagneticMixer,
    beaker: Beaker500,
    speed: int = Param(10, unit="rpm", min=1, max=100, desc="The speed of the magnetic stirrer."),
    time: int = Param(360, unit="sec", min=3, max=720, desc="The total time to mix the substances."),
) -> MagneticMixingOutputs:
    """Blend multiple substances into a homogeneous mixture with a magnetic stirrer."""
    return MagneticMixingOutputs(mixing_time=time)
