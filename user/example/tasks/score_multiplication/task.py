from pydantic import BaseModel

from eos import Param, task

from example.devices.analyzer.device import Analyzer


class ScoreOutputs(BaseModel):
    loss: int = Param(desc="How far the product is from 1024 and how large the initial number is.")


@task("Score Multiplication")
async def score_multiplication(
    analyzer: Analyzer,
    number: int = Param(desc="The number that was multiplied with some factors."),
    product: int = Param(desc="The final product after multiplying with some factors."),
) -> ScoreOutputs:
    """Score a multiplication by how close the product is to 1024 using an "analyzer" device."""
    return ScoreOutputs(loss=analyzer.analyze_result(number, product))
