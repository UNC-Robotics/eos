from eos.tasks.base_task import BaseTask


class ComputeMultiplicationObjective(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        resources: BaseTask.ResourcesType,
    ) -> BaseTask.OutputType | None:
        self.cancel_requested = False
        analyzer = devices["analyzer"]

        number = parameters["number"]
        product = parameters["product"]

        objective = analyzer.analyze_result(number, product)

        output_parameters = {"objective": objective}

        return output_parameters, None, None
