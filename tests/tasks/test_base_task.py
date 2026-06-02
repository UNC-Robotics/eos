from unittest.mock import Mock

import pytest

from eos.resources.entities.resource import Resource
from eos.utils.ray_utils import RayActorWrapper
from eos.tasks.base_task import BaseTask
from eos.tasks.exceptions import EosTaskExecutionError
from eos.tasks.input_file_handle import InputFileHandle


class FakeFileDb:
    """Minimal stand-in for FileDbInterface that records uploads in memory."""

    def __init__(self, files: dict[str, bytes] | None = None):
        self.stored: dict[str, bytes] = {}
        self._preloaded = files or {}

    async def store_file(self, key: str, data: bytes) -> None:
        self.stored[key] = data

    async def get_file(self, key: str) -> bytes:
        return self._preloaded[key]


class ConcreteTask(BaseTask):
    async def _execute(
        self, devices: BaseTask.DevicesType, parameters: BaseTask.ParametersType, resources: BaseTask.ResourcesType
    ) -> BaseTask.OutputType | None:
        return {"out_param": parameters["param1"]}, {"resource1": resources["resource1"]}, {"file.bin": b"content"}


class TestBaseTask:
    @pytest.fixture
    def concrete_task(self):
        return ConcreteTask("run_name", "task_name")

    @pytest.fixture
    def resource(self):
        return Resource(name="resource_name", type="beaker", meta={"location": "shelf"})

    def test_init(self):
        task = ConcreteTask("run_name", "task_name")
        assert task._protocol_run_name == "run_name"
        assert task._task_name == "task_name"

    @pytest.mark.asyncio
    async def test_execute_uploads_files_and_returns_names(self, concrete_task, resource):
        devices = {"device1": Mock(spec=RayActorWrapper)}
        parameters = {"param1": "value1"}
        resources = {"resource1": resource}
        fake_db = FakeFileDb()

        result = await concrete_task.execute(devices, parameters, resources, file_db_provider=lambda: fake_db)

        assert result[0] == {"out_param": "value1"}
        assert result[1] == {"resource1": resource}
        # The output files were uploaded to storage; only their names come back.
        assert result[2] == ["file.bin"]
        assert fake_db.stored == {"run_name/task_name/file.bin": b"content"}

    @pytest.mark.asyncio
    async def test_execute_failure(self, resource):
        class FailingTask(BaseTask):
            async def _execute(self, devices, parameters, resources) -> BaseTask.OutputType | None:
                raise ValueError("Test error")

        with pytest.raises(EosTaskExecutionError):
            await FailingTask("run_name", "task_name").execute({}, {"param1": "value1"}, {"resource1": resource})

    @pytest.mark.asyncio
    async def test_execute_empty_output(self):
        class EmptyOutputTask(BaseTask):
            async def _execute(self, devices, parameters, resources) -> BaseTask.OutputType | None:
                return None

        result = await EmptyOutputTask("run_name", "task_name").execute({}, {}, {})
        assert result == ({}, {}, [])

    @pytest.mark.asyncio
    async def test_execute_partial_output(self):
        class PartialOutputTask(BaseTask):
            async def _execute(self, devices, parameters, resources) -> BaseTask.OutputType | None:
                return {"out_param": "value"}, None, None

        result = await PartialOutputTask("run_name", "task_name").execute({}, {}, {})
        assert result == ({"out_param": "value"}, {}, [])

    @pytest.mark.asyncio
    async def test_automatic_input_resource_passthrough(self, resource):
        class InputResourcePassthroughTask(BaseTask):
            async def _execute(self, devices, parameters, resources) -> BaseTask.OutputType | None:
                return None

        result = await InputResourcePassthroughTask("run_name", "task_name").execute({}, {}, {"resource1": resource})
        assert result == ({}, {"resource1": resource}, [])

    @pytest.mark.asyncio
    async def test_missing_storage_when_files_returned_fails(self):
        with pytest.raises(EosTaskExecutionError, match="No file storage"):
            await ConcreteTask("run_name", "task_name").execute(
                {}, {"param1": "v"}, {"resource1": Resource(name="r", type="beaker")}
            )

    @pytest.mark.asyncio
    async def test_no_connection_opened_when_no_files(self):
        """A task that returns no files must never call the file-db provider."""

        class NoFilesTask(BaseTask):
            async def _execute(self, devices, parameters, resources) -> BaseTask.OutputType | None:
                return {"x": 1}, None, None

        def exploding_provider():
            raise AssertionError("provider must not be called when there are no files")

        result = await NoFilesTask("run_name", "task_name").execute({}, {}, {}, file_db_provider=exploding_provider)
        assert result == ({"x": 1}, {}, [])

    @pytest.mark.asyncio
    async def test_backward_compatible_dispatch_ignores_missing_params(self):
        """_execute declaring fewer than four params still runs without error."""

        class NoArgTask(BaseTask):
            async def _execute(self) -> BaseTask.OutputType | None:
                return {"ok": True}, None, None

        result = await NoArgTask("run_name", "task_name").execute({"d": 1}, {"p": 2}, {})
        assert result == ({"ok": True}, {}, [])

    @pytest.mark.asyncio
    async def test_files_input_is_passed_to_four_arg_execute(self):
        class FileConsumerTask(BaseTask):
            async def _execute(self, devices, parameters, resources, files) -> BaseTask.OutputType | None:
                data = await files["input"].read()
                return {"length": len(data)}, None, None

        fake_db = FakeFileDb(files={"run_name/gen/file.txt": b"hello"})
        files = {"input": InputFileHandle(lambda: fake_db, "run_name/gen/file.txt")}

        result = await FileConsumerTask("run_name", "task_name").execute({}, {}, {}, files)
        assert result == ({"length": 5}, {}, [])
