from eos.tasks.base_task import BaseTask


class ContainerUsage(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        resources: BaseTask.ResourcesType,
    ) -> BaseTask.OutputType | None:
        # For testing purposes, return empty outputs
        return {}, {}, {}
