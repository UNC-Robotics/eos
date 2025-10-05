from eos.tasks.base_task import BaseTask


class ScoreMultiplication(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        resources: BaseTask.ResourcesType,
    ) -> BaseTask.OutputType:
        analyzer = devices["analyzer"]
        loss = analyzer.analyze_result(parameters["number"], parameters["product"])
        output_parameters = {"loss": loss}

        return output_parameters, None, None
