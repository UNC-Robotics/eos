import traceback
from logging import Handler, LogRecord

from eos.logging.log_buffer import log_buffer


class BufferHandler(Handler):
    """Lightweight logging handler that writes to in-memory ring buffer."""

    def emit(self, record: LogRecord) -> None:
        msg = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            msg += "\n" + "".join(traceback.format_exception(*record.exc_info))
        log_buffer.append(
            {
                "t": record.created,
                "l": record.levelname,
                "m": msg,
                "s": f"{record.filename}:{record.lineno}",
            }
        )
