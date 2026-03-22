import traceback
from datetime import UTC, datetime
from logging import Handler, LogRecord
from typing import ClassVar

from rich.console import Console


class RichConsoleHandler(Handler):
    """
    A logging handler that uses the Rich library to print logs to the console.
    """

    _LOG_COLORS: ClassVar = {
        "DEBUG": "[cyan]",
        "INFO": "[green]",
        "WARNING": "[yellow]",
        "ERROR": "[bold red]",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.console = Console()
        self._tz = datetime.now(UTC).astimezone().tzinfo

    def emit(self, record: LogRecord) -> None:
        time = datetime.fromtimestamp(record.created, tz=self._tz).strftime("%m/%d/%Y %H:%M:%S")
        level = record.levelname
        filename = record.filename
        line_no = record.lineno

        log_prefix = f"{self._LOG_COLORS.get(level, '[white]')}{level}[/] {time} {filename}:{line_no} -"
        msg = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            msg += "\n" + "".join(traceback.format_exception(*record.exc_info))
        self.console.print(f"{log_prefix} {msg}")
