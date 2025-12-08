from eos.tasks.base_task import BaseTask


class Multiplication(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        resources: BaseTask.ResourcesType,
    ) -> BaseTask.OutputType:
        multiplier = devices["multiplier"]
        product = multiplier.multiply(parameters["number"], parameters["factor"])
        output_parameters = {"in_number": parameters["number"], "product": product}

        return output_parameters, None, None
