import asyncio
import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

from eos.resources.entities.resource import Resource
from eos.utils.ray_utils import RayActorWrapper
from eos.database.file_db_interface import FileDbInterface
from eos.tasks.exceptions import EosTaskExecutionError
from eos.tasks.input_file_handle import InputFileHandle


def build_task_output_file_path(protocol_run_name: str | None, task_name: str, file_name: str) -> str:
    """Build the SeaweedFS key for a task output file."""
    prefix = protocol_run_name if protocol_run_name is not None else "on_demand"
    return f"{prefix}/{task_name}/{file_name}"


class BaseTask(ABC):
    """Base class for all tasks in EOS."""

    DevicesType = dict[str, RayActorWrapper]
    ParametersType = dict[str, Any]
    ResourcesType = dict[str, Resource]
    FilesType = dict[str, bytes]
    InputFilesType = dict[str, InputFileHandle]
    OutputType = tuple[ParametersType, ResourcesType, FilesType]
    MAX_OUTPUT_LENGTH = 3
    NUM_EXECUTE_INPUTS = 4  # devices, parameters, resources, files

    _execute_arity_cache: ClassVar[dict[type, int]] = {}

    def __init__(self, protocol_run_name: str | None, task_name: str) -> None:
        self._protocol_run_name = protocol_run_name
        self._task_name = task_name

    async def execute(
        self,
        devices: DevicesType | None = None,
        parameters: ParametersType | None = None,
        resources: ResourcesType | None = None,
        files: InputFilesType | None = None,
        file_db_provider: Callable[[], FileDbInterface] | None = None,
    ) -> tuple[ParametersType, ResourcesType, list[str]]:
        """Execute a task, then upload its output files and return their names."""
        try:
            inputs = (devices or {}, parameters or {}, resources or {}, files or {})
            output = await self._execute(*inputs[: self._execute_arity()])

            output_parameters, output_resources, output_files = ({}, {}, {})

            if output:
                output_parameters = output[0] if len(output) > 0 and output[0] is not None else {}
                output_resources = output[1] if len(output) > 1 and output[1] is not None else {}
                output_files = output[2] if len(output) == BaseTask.MAX_OUTPUT_LENGTH and output[2] is not None else {}

            if resources:
                output_resources = {**resources, **output_resources}

            output_file_names = await self._upload_output_files(output_files, file_db_provider)

            return output_parameters, output_resources, output_file_names
        except Exception as e:
            raise EosTaskExecutionError(f"Error executing task {self._task_name}: {e!s}") from e

    async def _upload_output_files(
        self, output_files: FilesType, file_db_provider: Callable[[], FileDbInterface] | None
    ) -> list[str]:
        """Upload all output files to SeaweedFS concurrently and return their names. Gates task completion."""
        if not output_files:
            return []
        if file_db_provider is None:
            raise EosTaskExecutionError(f"No file storage available to upload outputs of task '{self._task_name}'.")

        file_db = file_db_provider()
        await asyncio.gather(
            *(
                file_db.store_file(build_task_output_file_path(self._protocol_run_name, self._task_name, name), data)
                for name, data in output_files.items()
            )
        )
        return list(output_files.keys())

    @classmethod
    def _execute_arity(cls) -> int:
        """How many leading canonical inputs this subclass's _execute accepts (so omitted ones are not passed)."""
        cached = BaseTask._execute_arity_cache.get(cls)
        if cached is not None:
            return cached

        params = [p for name, p in inspect.signature(cls._execute).parameters.items() if name != "self"]
        if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params):
            arity = BaseTask.NUM_EXECUTE_INPUTS
        else:
            positional = [
                p
                for p in params
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            arity = min(len(positional), BaseTask.NUM_EXECUTE_INPUTS)

        BaseTask._execute_arity_cache[cls] = arity
        return arity

    @abstractmethod
    async def _execute(
        self,
        devices: DevicesType | None = None,
        parameters: ParametersType | None = None,
        resources: ResourcesType | None = None,
        files: InputFilesType | None = None,
    ) -> OutputType | None:
        """Implementation for the execution of a task. All parameters are optional."""
