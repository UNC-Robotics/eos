from pydantic import BaseModel

from eos import Param, task

from testing.devices.multiplication_lab.analyzer.device import Analyzer


class ObjectiveOutputs(BaseModel):
    objective: int = Param(desc="The objective for the optimize_multiplication protocol.")


@task("Compute Multiplication Objective")
async def compute_multiplication_objective(
    analyzer: Analyzer,
    number: int = Param(desc="The number to multiply."),
    product: int = Param(desc="The final product."),
) -> ObjectiveOutputs:
    """Compute the objective for the optimize_multiplication protocol."""
    return ObjectiveOutputs(objective=analyzer.analyze_result(number, product))
