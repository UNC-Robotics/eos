from eos.tasks.base_task import BaseTask


class MagneticMixingTask(BaseTask):
    def _execute(
        self,
        devices: BaseTask.DevicesType,
        parameters: BaseTask.ParametersType,
        containers: BaseTask.ContainersType,
    ) -> BaseTask.OutputType:
        output_parameters = {"mixing_time": parameters["time"]}

        return output_parameters, None, None