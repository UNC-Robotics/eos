from eos.tasks.base_task import BaseTask


class Multiplication(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        resources: BaseTask.ResourcesType,
    ) -> BaseTask.OutputType | None:
        multiplier = devices["multiplier"]
        number = parameters["number"]
        factor = parameters["factor"]

        product = multiplier.multiply(number, factor)

        output_parameters = {"product": product}

        return output_parameters, None, None
