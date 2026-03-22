import pytest

import eos.configuration.env
from eos.utils import profiler


def pytest_addoption(parser):
    parser.addoption("--profile", action="store_true", default=False, help="Enable EOS function profiling report")


def pytest_sessionstart(session):
    if session.config.getoption("--profile"):
        profiler.start()


def pytest_sessionfinish(session, exitstatus):
    if session.config.getoption("--profile"):
        profiler.report()


def pytest_collection_modifyitems(items):
    """Sort tests by the slow marker. Tests with the slow marker will be executed last."""

    def weight(item):
        return 1 if item.get_closest_marker("slow") else 0

    items.sort(key=weight)
