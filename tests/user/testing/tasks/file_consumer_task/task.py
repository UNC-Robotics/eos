from eos.tasks.base_task import BaseTask


class FileConsumer(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        resources: BaseTask.ResourcesType,
        files: BaseTask.InputFilesType,
    ) -> BaseTask.OutputType | None:
        data = await files["input"].read()
        return {"length": len(data)}, None, None
