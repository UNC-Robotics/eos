from typing import Any

from eos.devices.base_device import BaseDevice


class Analyzer(BaseDevice):
    """Analyzes the multiplication result to produce a loss."""

    async def _initialize(self, init_parameters: dict[str, Any]) -> None:
        pass

    async def _cleanup(self) -> None:
        pass

    async def _report(self) -> dict[str, Any]:
        pass

    def analyze_result(self, number: int, product: int) -> int:
        return number + 100 * abs(product - 1024)
