from typing import Any

from eos import Device


class MagneticMixer(Device, type="magnetic_mixer"):
    """Magnetic mixer for mixing substances."""

    class Config(Device.Config):
        max_speed: int = 100

    async def _initialize(self, config: Config) -> None:
        self.max_speed = config.max_speed

    async def _report(self) -> dict[str, Any]:
        return {"max_speed": self.max_speed}
