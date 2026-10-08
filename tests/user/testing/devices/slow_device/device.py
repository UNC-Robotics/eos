import time

from eos import Device


class SlowDevice(Device, type="slow_device"):
    """Device whose cleanup blocks, for testing timeouts."""

    class Config(Device.Config):
        cleanup_delay: float = 0

    async def _initialize(self, config: Config) -> None:
        self.cleanup_delay = config.cleanup_delay

    async def _cleanup(self) -> None:
        time.sleep(self.cleanup_delay)  # noqa: ASYNC251 Blocks the actor so it stops answering status checks
