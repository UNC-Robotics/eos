from abc import ABC, abstractmethod
from typing import Any
import traceback

from eos.resources.entities.resource import Resource
from eos.utils.ray_utils import RayActorWrapper
from eos.tasks.exceptions import EosTaskExecutionError


class BaseTask(ABC):
    """Base class for all tasks in EOS."""

    DevicesType = dict[str, RayActorWrapper]
    ParametersType = dict[str, Any]
    ResourcesType = dict[str, Resource]
    FilesType = dict[str, bytes]
    OutputType = tuple[ParametersType, ResourcesType, FilesType]
    MAX_OUTPUT_LENGTH = 3

    def __init__(self, experiment_name: str, task_name: str) -> None:
        self._experiment_name = experiment_name
        self._task_name = task_name

    async def execute(
        self, devices: DevicesType, parameters: ParametersType, resources: ResourcesType
    ) -> OutputType | None:
        """Execute a task with the given input and return the output."""
        try:
            output = await self._execute(devices, parameters, resources)

            output_parameters, output_resources, output_files = ({}, {}, {})

            if output:
                output_parameters = output[0] if len(output) > 0 and output[0] is not None else {}
                output_resources = output[1] if len(output) > 1 and output[1] is not None else {}
                output_files = output[2] if len(output) == BaseTask.MAX_OUTPUT_LENGTH and output[2] is not None else {}

            if resources:
                output_resources = {**resources, **output_resources}

            return output_parameters, output_resources, output_files
        except Exception as e:
            raise EosTaskExecutionError(
                f"Error executing task {self._task_name}: {e!s}\n{traceback.format_exc()}"
            ) from e

    @abstractmethod
    async def _execute(
        self, devices: DevicesType, parameters: ParametersType, resources: ResourcesType
    ) -> OutputType | None:
        """Implementation for the execution of a task."""
