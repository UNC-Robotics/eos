from pydantic import BaseModel

from eos import Param, task

from testing.devices.analytical_lab.balance.device import Balance


class WeighContainerOutputs(BaseModel):
    weight: float = Param(unit="g", desc="The measured weight of the container.")


@task("Weigh Container")
async def weigh_container(
    balance: Balance,
    minimum_weight: float = Param(0.1, unit="g", min=0.0001, desc="The minimum weight for a valid measurement."),
) -> WeighContainerOutputs:
    """Measure the mass of a container with an analytical balance."""
    return WeighContainerOutputs(weight=0.0)
