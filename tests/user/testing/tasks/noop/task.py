from eos import task


@task("Noop")
async def noop() -> None:
    """This task does nothing."""
