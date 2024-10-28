import random

from eos.tasks.base_task import BaseTask


class FileGeneration(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        containers: BaseTask.ContainersType,
    ) -> BaseTask.OutputType:
        content_length = parameters["content_length"]

        file_content = "".join(
            random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=content_length)
        )

        return None, None, {"file.txt": bytes(file_content, "utf-8")}
