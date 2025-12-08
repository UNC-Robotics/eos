from datetime import datetime
from logging import Handler, LogRecord
from pathlib import Path
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

    def emit(self, record: LogRecord) -> None:
        time = datetime.now().astimezone().strftime("%m/%d/%Y %H:%M:%S")
        level = record.levelname
        filename = Path(record.pathname).name
        line_no = record.lineno

        log_prefix = f"{self._LOG_COLORS.get(level, '[white]')}{level}[/] {time} {filename}:{line_no} -"
        self.console.print(f"{log_prefix} {record.getMessage()}")
