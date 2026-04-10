import logging
from enum import Enum

from eos.logging.buffer_handler import BufferHandler
from eos.logging.rich_console_handler import RichConsoleHandler


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Logger:
    """
    The Logger class is used to log all kinds of messages in EOS. It provides a simple interface
    for logging messages at different levels.
    """

    def __init__(self):
        self.logger = logging.getLogger("rich")
        self.logger.name = "eos"
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(RichConsoleHandler())
        self.logger.addHandler(BufferHandler())

    def set_level(self, level: LogLevel | str) -> None:
        if isinstance(level, str):
            level = LogLevel(level)
        self.logger.setLevel(level.value)

    def debug(self, message: str, *args, **kwargs) -> None:
        stacklevel = kwargs.pop("stacklevel", 2)
        self.logger.debug(message, *args, **kwargs, stacklevel=stacklevel)

    def info(self, message: str, *args, **kwargs) -> None:
        stacklevel = kwargs.pop("stacklevel", 2)
        self.logger.info(message, *args, **kwargs, stacklevel=stacklevel)

    def warning(self, message: str, *args, **kwargs) -> None:
        stacklevel = kwargs.pop("stacklevel", 2)
        self.logger.warning(message, *args, **kwargs, stacklevel=stacklevel)

    def error(self, message: str, *args, **kwargs) -> None:
        stacklevel = kwargs.pop("stacklevel", 2)
        self.logger.error(message, *args, **kwargs, stacklevel=stacklevel)


log = Logger()
