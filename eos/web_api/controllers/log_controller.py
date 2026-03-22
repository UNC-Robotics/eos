import json
from collections.abc import AsyncGenerator

from litestar import Controller, get
from litestar.response.sse import ServerSentEvent, ServerSentEventMessage

from eos.logging.log_buffer import log_buffer

LEVEL_PRIORITY = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}


class LogController(Controller):
    path = "/logs"

    @get("/stream")
    async def stream_logs(self, level: str = "INFO") -> ServerSentEvent:
        """
        SSE endpoint that streams log entries in real-time.

        Query params:
          level: minimum log level (DEBUG, INFO, WARNING, ERROR)
        """
        min_level = LEVEL_PRIORITY.get(level.upper(), 1)

        async def event_generator() -> AsyncGenerator[ServerSentEventMessage, None]:
            last_seq = log_buffer.current_sequence

            # Send recent buffered entries on connect
            recent = log_buffer.get_recent(100)
            for entry in recent:
                if LEVEL_PRIORITY.get(entry.get("l", ""), 0) >= min_level:
                    yield ServerSentEventMessage(data=json.dumps(entry), event="log")
                    last_seq = entry.get("seq", last_seq)

            # Stream new entries as they arrive
            while not log_buffer.is_shutdown:
                has_new = await log_buffer.wait_for_new(wait_seconds=30)
                if has_new:
                    entries = log_buffer.get_since(last_seq)
                    for entry in entries:
                        if LEVEL_PRIORITY.get(entry.get("l", ""), 0) >= min_level:
                            yield ServerSentEventMessage(data=json.dumps(entry), event="log")
                        last_seq = entry.get("seq", last_seq)
                else:
                    # Keepalive on timeout
                    yield ServerSentEventMessage(comment="keepalive")

        return ServerSentEvent(event_generator())

    @get("/history")
    async def get_log_history(self, level: str = "DEBUG", limit: int = 200) -> dict:
        """Get recent log entries (non-streaming, for initial page load)."""
        min_level = LEVEL_PRIORITY.get(level.upper(), 0)
        recent = log_buffer.get_recent(limit * 2)  # fetch extra to account for filtering
        filtered = [e for e in recent if LEVEL_PRIORITY.get(e.get("l", ""), 0) >= min_level]
        return {
            "entries": filtered[-limit:],
            "sequence": log_buffer.current_sequence,
        }
