from eos.tasks.base_task import BaseTask


class HplcAnalysisTask(BaseTask):
    def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        containers: BaseTask.ContainersType,
    ) -> BaseTask.OutputType:
        pass