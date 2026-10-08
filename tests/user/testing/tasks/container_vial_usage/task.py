from eos import task

from testing.resources import Vial


@task("Container Vial Usage")
async def container_vial_usage(sample: Vial) -> None:
    """Task that requires a vial container input for testing."""
