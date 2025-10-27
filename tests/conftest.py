import asyncio
import os

import pytest

# Suppress Ray GPU override warning
os.environ.setdefault("RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO", "0")


@pytest.fixture(scope="session")
def event_loop():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def pytest_collection_modifyitems(items):
    """Sort tests by the slow marker. Tests with the slow marker will be executed last."""

    def weight(item):
        return 1 if item.get_closest_marker("slow") else 0

    items.sort(key=weight)
