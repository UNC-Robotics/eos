from eos.tasks.base_task import BaseTask


class Multiplication(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        containers: BaseTask.ContainersType,
    ) -> BaseTask.OutputType:
        multiplier = devices.get_all_by_type("multiplier")[0]
        product = multiplier.multiply(parameters["number"], parameters["factor"])
        output_parameters = {"product": product}

        return output_parameters, None, None
