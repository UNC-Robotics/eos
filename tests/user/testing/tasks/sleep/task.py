import asyncio

from eos import Param, task


@task("Sleep")
async def sleep(time: int = Param(0, unit="sec", min=0, desc="How long to sleep.")) -> None:
    """This task sleeps for the specified amount of time."""
    await asyncio.sleep(time)
