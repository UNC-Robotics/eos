from eos.tasks.base_task import BaseTask


class Purification(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        containers: BaseTask.ContainersType,
    ) -> BaseTask.OutputType:
        output_parameters = {"water_salinity": 0.02}

        return output_parameters, None, None
