import asyncio
from collections import deque
from typing import Any


class LogBuffer:
    """Thread-safe in-memory ring buffer for log entries with async notification."""

    def __init__(self, maxlen: int = 2000):
        self._buffer: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sequence: int = 0
        self._shutdown: bool = False

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind to the running event loop. Call once after asyncio.run() starts."""
        self._loop = loop
        self._event = asyncio.Event()

    def append(self, entry: dict[str, Any]) -> None:
        """Append a log entry. Thread-safe."""
        self._sequence += 1
        entry["seq"] = self._sequence
        self._buffer.append(entry)
        if self._loop is not None and self._event is not None:
            self._loop.call_soon_threadsafe(self._event.set)

    async def wait_for_new(self, wait_seconds: float = 30) -> bool:
        """Await new entries. Returns True if new data arrived, False on timeout."""
        if self._event is None:
            await asyncio.sleep(wait_seconds)
            return False
        try:
            async with asyncio.timeout(wait_seconds):
                await self._event.wait()
            self._event.clear()
            return True
        except TimeoutError:
            return False

    def get_recent(self, n: int = 200) -> list[dict[str, Any]]:
        """Return the last n entries."""
        items = list(self._buffer)
        return items[-n:]

    def get_since(self, after_seq: int) -> list[dict[str, Any]]:
        """Return entries with sequence number > after_seq."""
        return [e for e in self._buffer if e.get("seq", 0) > after_seq]

    def shutdown(self) -> None:
        """Signal all waiting generators to stop."""
        self._shutdown = True
        if self._loop is not None and self._event is not None:
            self._loop.call_soon_threadsafe(self._event.set)

    @property
    def is_shutdown(self) -> bool:
        return self._shutdown

    @property
    def current_sequence(self) -> int:
        return self._sequence


log_buffer = LogBuffer()
