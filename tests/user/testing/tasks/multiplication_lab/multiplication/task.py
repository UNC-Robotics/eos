from pydantic import BaseModel

from eos import Param, task

from testing.devices.multiplication_lab.multiplier.device import Multiplier


class MultiplicationOutputs(BaseModel):
    product: int = Param(desc="The product of the number and the factor.")


@task("Multiplication")
async def multiplication(
    multiplier: Multiplier,
    number: int = Param(desc="The number to multiply."),
    factor: int = Param(desc="The factor to multiply the number by."),
) -> MultiplicationOutputs:
    """Multiply a number by a factor."""
    return MultiplicationOutputs(product=multiplier.multiply(number, factor))
