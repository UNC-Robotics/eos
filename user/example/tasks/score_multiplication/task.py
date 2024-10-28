from eos.tasks.base_task import BaseTask


class ScoreMultiplication(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        containers: BaseTask.ContainersType,
    ) -> BaseTask.OutputType:
        analyzer = devices.get_all_by_type("analyzer")[0]
        loss = analyzer.analyze_result(parameters["number"], parameters["product"])
        output_parameters = {"loss": loss}

        return output_parameters, None, None
