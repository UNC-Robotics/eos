from typing import Any

from eos.devices.base_device import BaseDevice


class Multiplier(BaseDevice):
    async def _initialize(self, init_parameters: dict[str, Any]) -> None:
        pass

    async def _cleanup(self) -> None:
        pass

    async def _report(self) -> dict[str, Any]:
        pass

    def multiply(self, a: int, b: int) -> int:
        return a * b
