from collections.abc import AsyncIterable

from eos.tasks.task_manager import TaskManager


class ResultModule:
    """
    Top-level result querying integration.
    Exposes an interface for querying results, such as downloading task output files.
    """

    def __init__(self, task_manager: TaskManager):
        self._task_manager = task_manager

    def download_task_output_file(
        self, experiment_id: str, task_id: str, file_name: str, chunk_size: int = 3 * 1024 * 1024
    ) -> AsyncIterable[bytes]:
        """
        Stream the contents of a task output file in chunks.
        """
        return self._task_manager.stream_task_output_file(experiment_id, task_id, file_name, chunk_size)

    async def list_task_output_files(self, experiment_id: str, task_id: str) -> list[str]:
        """
        Get a list of all output files for a given task.
        """
        return self._task_manager.list_task_output_files(experiment_id, task_id)
