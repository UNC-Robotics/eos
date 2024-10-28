import asyncio
import time

from eos.tasks.base_task import BaseTask


class Sleep(BaseTask):
    async def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        containers: BaseTask.ContainersType,
    ) -> BaseTask.OutputType:
        self.cancel_requested = False

        sleep_time = parameters["time"]
        start_time = time.time()
        elapsed = 0

        while elapsed < sleep_time:
            if self.cancel_requested:
                self.cancel_requested = False
                return None
            await asyncio.sleep(1)
            elapsed = time.time() - start_time

        return None
