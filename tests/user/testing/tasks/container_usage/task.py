from eos import task

from testing.resources import Beaker500


@task("Container Usage")
async def container_usage(sample: Beaker500) -> None:
    """Task that requires a single container input for testing."""
