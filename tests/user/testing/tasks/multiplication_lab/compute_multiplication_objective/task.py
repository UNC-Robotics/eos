from eos.tasks.base_task import BaseTask


class ComputeMultiplicationObjective(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        containers: BaseTask.ContainersType,
    ) -> BaseTask.OutputType:
        self.cancel_requested = False
        analyzer = devices.get_all_by_type("analyzer")[0]

        number = parameters["number"]
        product = parameters["product"]

        objective = analyzer.analyze_result(number, product)

        output_parameters = {"objective": objective}

        return output_parameters, None, None
