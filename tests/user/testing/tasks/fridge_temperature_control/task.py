from eos import Param, task

from testing.devices.small_lab.fridge.device import Fridge


@task("Fridge Temperature Control")
async def fridge_temperature_control(
    fridge: Fridge,
    target_temperature: int = Param(unit="celsius", min=-20, max=10, desc="The new temperature for the fridge."),
) -> None:
    """Adjust the temperature of a laboratory refrigerator to a specified target."""
