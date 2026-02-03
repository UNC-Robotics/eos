from unittest.mock import Mock

import pytest

from eos.resources.entities.resource import Resource
from eos.utils.ray_utils import RayActorWrapper
from eos.tasks.base_task import BaseTask
from eos.tasks.exceptions import EosTaskExecutionError


class ConcreteTask(BaseTask):
    async def _execute(
        self, devices: BaseTask.DevicesType, parameters: BaseTask.ParametersType, resources: BaseTask.ResourcesType
    ) -> BaseTask.OutputType | None:
        return {"out_param": parameters["param1"]}, {"resource1": resources["resource1"]}, {"file.bin": b"content"}


class TestBaseTask:
    @pytest.fixture
    def concrete_task(self):
        return ConcreteTask("exp_name", "task_name")

    @pytest.fixture
    def resource(self):
        return Resource(name="resource_name", type="beaker", meta={"location": "shelf"})

    def test_init(self):
        task = ConcreteTask("exp_name", "task_name")
        assert task._experiment_name == "exp_name"
        assert task._task_name == "task_name"

    @pytest.mark.asyncio
    async def test_execute_success(self, concrete_task, resource):
        devices = {"device1": Mock(spec=RayActorWrapper)}
        parameters = {"param1": "value1"}
        resources = {"resource1": resource}

        result = await concrete_task.execute(devices, parameters, resources)

        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], dict)
        assert isinstance(result[1], dict)
        assert isinstance(result[2], dict)
        assert result[0] == {"out_param": "value1"}
        assert result[1] == {"resource1": resource}
        assert result[2] == {"file.bin": b"content"}

    @pytest.mark.asyncio
    async def test_execute_failure(self, resource):
        class FailingTask(BaseTask):
            async def _execute(
                self,
                devices: BaseTask.DevicesType,
                parameters: BaseTask.ParametersType,
                resources: BaseTask.ResourcesType,
            ) -> BaseTask.OutputType | None:
                raise ValueError("Test error")

        devices = {"device1": Mock(spec=RayActorWrapper)}
        parameters = {"param1": "value1"}
        resources = {"resource1": resource}

        failing_task = FailingTask("exp_name", "task_name")
        with pytest.raises(EosTaskExecutionError):
            await failing_task.execute(devices, parameters, resources)

    @pytest.mark.asyncio
    async def test_execute_empty_output(self, concrete_task):
        class EmptyOutputTask(BaseTask):
            async def _execute(
                self,
                devices: BaseTask.DevicesType,
                parameters: BaseTask.ParametersType,
                resources: BaseTask.ResourcesType,
            ) -> BaseTask.OutputType | None:
                return None

        task = EmptyOutputTask("exp_name", "task_name")
        result = await task.execute({}, {}, {})

        assert result == ({}, {}, {})

    @pytest.mark.asyncio
    async def test_execute_partial_output(self, concrete_task):
        class PartialOutputTask(BaseTask):
            async def _execute(
                self,
                devices: BaseTask.DevicesType,
                parameters: BaseTask.ParametersType,
                resources: BaseTask.ResourcesType,
            ) -> BaseTask.OutputType | None:
                return {"out_param": "value"}, None, None

        task = PartialOutputTask("exp_name", "task_name")
        result = await task.execute({}, {}, {})

        assert result == ({"out_param": "value"}, {}, {})

    @pytest.mark.asyncio
    async def test_automatic_input_resource_passthrough(self, concrete_task, resource):
        class InputResourcePassthroughTask(BaseTask):
            async def _execute(
                self,
                devices: BaseTask.DevicesType,
                parameters: BaseTask.ParametersType,
                resources: BaseTask.ResourcesType,
            ) -> BaseTask.OutputType | None:
                return None

        task = InputResourcePassthroughTask("exp_name", "task_name")
        result = await task.execute({}, {}, {"resource1": resource})

        assert result == ({}, {"resource1": resource}, {})
