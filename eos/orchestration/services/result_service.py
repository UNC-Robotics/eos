from collections.abc import AsyncIterable

from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject


class ResultService:
    """
    Top-level result querying integration.
    Exposes an interface for querying results, such as downloading task output files.
    """

    @inject
    def __init__(self, task_manager: TaskManager):
        self._task_manager = task_manager

    def download_task_output_file(
        self, experiment_name: str, task_name: str, file_name: str, chunk_size: int = 3 * 1024 * 1024
    ) -> AsyncIterable[bytes]:
        """
        Stream the contents of a task output file in chunks.
        """
        return self._task_manager.stream_task_output_file(experiment_name, task_name, file_name, chunk_size)

    async def list_task_output_files(self, experiment_name: str, task_name: str) -> list[str]:
        """
        Get a list of all output files for a given task.
        """
        return self._task_manager.list_task_output_files(experiment_name, task_name)
