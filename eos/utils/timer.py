import time
from typing import ClassVar


class Timer:
    """
    A context manager for timing code execution.

    The elapsed time is stored internally in seconds, and the desired unit can be
    specified when retrieving the duration.

    Supported units:

    - ``s``: seconds
    - ``ms``: milliseconds (default)
    - ``us``: microseconds
    - ``ns``: nanoseconds

    Example usage:

    .. code-block:: python

       with Timer() as timer:
           # your code block here
           pass
       print("Elapsed time:", timer.get_duration("ms"))
    """

    _unit_factors: ClassVar = {
        "s": 1,
        "ms": 1000,
        "us": 1e6,
        "ns": 1e9,
    }

    def __init__(self):
        """Initialize the Timer."""
        self._duration = None

    def __enter__(self):
        """
        Start the timer upon entering the context.

        :return: The Timer instance.
        :rtype: Timer
        """
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Stop the timer upon exiting the context.

        :param exc_type: The type of exception raised (if any).
        :param exc_val: The exception instance raised (if any).
        :param exc_tb: The traceback of the exception raised (if any).
        """
        self._duration = time.perf_counter() - self.start

    def get_duration(self, unit="ms") -> float:
        """
        Retrieve the elapsed time as a formatted string with the specified unit.

        :param unit: The unit for the elapsed time. Supported values are
                     ``'s'``, ``'ms'``, ``'us'``, or ``'ns'``. Defaults to ``'s'``.
        :type unit: str
        :return: The elapsed time in the specified unit.
        """
        if self._duration is None:
            raise ValueError("Timer hasn't been stopped yet. Use it as a context manager.")
        if unit not in self._unit_factors:
            raise ValueError(f"Unsupported unit {unit}. Choose from {list(self._unit_factors.keys())}.")

        factor = self._unit_factors[unit]
        return self._duration * factor

    def __str__(self):
        """
        Return the elapsed time as a string if available, otherwise indicate that the timer is not finished.

        :return: The elapsed time with its unit, or a message stating that the timer is not finished.
        :rtype: str
        """
        return self.get_duration() if self._duration is not None else "Timer not finished yet"
