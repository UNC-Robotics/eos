from pydantic import BaseModel

from eos import Param, task

from example.devices.multiplier.device import Multiplier


class MultiplicationOutputs(BaseModel):
    in_number: int = Param(desc="The number to multiply that was given as input.")
    product: int = Param(desc="The product of the number and the factor.")


@task("Multiplication")
async def multiplication(
    multiplier: Multiplier,
    number: int = Param(desc="The number to multiply."),
    factor: int = Param(desc="The factor to multiply the number by."),
) -> MultiplicationOutputs:
    """Multiply a number by a factor using a "multiplier" device."""
    return MultiplicationOutputs(in_number=number, product=multiplier.multiply(number, factor))
