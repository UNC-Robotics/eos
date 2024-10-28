from unittest.mock import Mock

import pytest

from eos.containers.entities.container import Container
from eos.devices.device_actor_wrapper_registry import DeviceActorWrapperRegistry
from eos.tasks.base_task import BaseTask
from eos.tasks.exceptions import EosTaskExecutionError


class ConcreteTask(BaseTask):
    async def _execute(
        self, devices: BaseTask.DevicesType, parameters: BaseTask.ParametersType, containers: BaseTask.ContainersType
    ) -> BaseTask.OutputType | None:
        return {"out_param": parameters["param1"]}, {"container1": containers["container1"]}, {"file": b"content"}


class TestBaseTask:
    @pytest.fixture
    def concrete_task(self):
        return ConcreteTask("exp_id", "task_id")

    @pytest.fixture
    def container(self):
        return Container(id="container_id", type="beaker", lab="lab", location="shelf")

    def test_init(self):
        task = ConcreteTask("exp_id", "task_id")
        assert task._experiment_id == "exp_id"
        assert task._task_id == "task_id"

    @pytest.mark.asyncio
    async def test_execute_success(self, concrete_task, container):
        devices = {"device1": Mock(spec=DeviceActorWrapperRegistry)}
        parameters = {"param1": "value1"}
        containers = {"container1": container}

        result = await concrete_task.execute(devices, parameters, containers)

        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], dict)
        assert isinstance(result[1], dict)
        assert isinstance(result[2], dict)
        assert result[0] == {"out_param": "value1"}
        assert result[1] == {"container1": container}
        assert result[2] == {"file": b"content"}

    @pytest.mark.asyncio
    async def test_execute_failure(self, container):
        class FailingTask(BaseTask):
            async def _execute(
                self,
                devices: BaseTask.DevicesType,
                parameters: BaseTask.ParametersType,
                containers: BaseTask.ContainersType,
            ) -> BaseTask.OutputType | None:
                raise ValueError("Test error")

        devices = {"device1": Mock(spec=DeviceActorWrapperRegistry)}
        parameters = {"param1": "value1"}
        containers = {"container1": container}

        failing_task = FailingTask("exp_id", "task_id")
        with pytest.raises(EosTaskExecutionError):
            await failing_task.execute(devices, parameters, containers)

    @pytest.mark.asyncio
    async def test_execute_empty_output(self, concrete_task):
        class EmptyOutputTask(BaseTask):
            async def _execute(
                self,
                devices: BaseTask.DevicesType,
                parameters: BaseTask.ParametersType,
                containers: BaseTask.ContainersType,
            ) -> BaseTask.OutputType | None:
                return None

        task = EmptyOutputTask("exp_id", "task_id")
        result = await task.execute({}, {}, {})

        assert result == ({}, {}, {})

    @pytest.mark.asyncio
    async def test_execute_partial_output(self, concrete_task):
        class PartialOutputTask(BaseTask):
            async def _execute(
                self,
                devices: BaseTask.DevicesType,
                parameters: BaseTask.ParametersType,
                containers: BaseTask.ContainersType,
            ) -> BaseTask.OutputType | None:
                return {"out_param": "value"}, None, None

        task = PartialOutputTask("exp_id", "task_id")
        result = await task.execute({}, {}, {})

        assert result == ({"out_param": "value"}, {}, {})

    @pytest.mark.asyncio
    async def test_automatic_input_container_passthrough(self, concrete_task, container):
        class InputContainerPassthroughTask(BaseTask):
            async def _execute(
                self,
                devices: BaseTask.DevicesType,
                parameters: BaseTask.ParametersType,
                containers: BaseTask.ContainersType,
            ) -> BaseTask.OutputType | None:
                return None

        task = InputContainerPassthroughTask("exp_id", "task_id")
        result = await task.execute({}, {}, {"container1": container})

        assert result == ({}, {"container1": container}, {})
