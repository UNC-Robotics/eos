import asyncio


class WorkSignal:
    """
    Event-based signaling for immediate work wake-up.

    Used to wake the orchestrator's spin loop instantly when new work
    is submitted, eliminating polling latency for idle-to-busy transitions.
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()

    async def wait(self, max_wait: float | None = None) -> bool:
        """
        Wait for a work signal.

        :param max_wait: Maximum time to wait in seconds. None for infinite wait.
        :return: True if signaled, False if timeout occurred.
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout=max_wait)
            return True
        except TimeoutError:
            return False

    def signal(self) -> None:
        """Signal that work is available - wakes any waiting coroutine."""
        self._event.set()

    def clear(self) -> None:
        """Clear the signal after processing."""
        self._event.clear()
