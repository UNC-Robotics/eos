import asyncio
from collections.abc import AsyncIterable
from datetime import datetime, timezone
from typing import Any

from eos.configuration.configuration_manager import ConfigurationManager
from eos.experiments.repositories.experiment_repository import ExperimentRepository
from eos.logging.logger import log
from eos.persistence.async_mongodb_interface import AsyncMongoDbInterface
from eos.persistence.file_db_interface import FileDbInterface
from eos.tasks.entities.task import Task, TaskStatus, TaskOutput, TaskDefinition
from eos.tasks.exceptions import EosTaskStateError, EosTaskExistsError
from eos.tasks.repositories.task_repository import TaskRepository


class TaskManager:
    """
    Manages the state of all tasks in EOS.
    """

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        db_interface: AsyncMongoDbInterface,
        file_db_interface: FileDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._file_db_interface = file_db_interface
        self._session_factory = db_interface.session_factory
        self._tasks = None
        self._experiments = None

    async def initialize(self, db_interface: AsyncMongoDbInterface) -> None:
        self._tasks = TaskRepository(db_interface)
        await self._tasks.initialize()

        self._experiments = ExperimentRepository(db_interface)
        await self._experiments.initialize()

        log.debug("Task manager initialized.")

    async def create_task(self, task_definition: TaskDefinition) -> None:
        """
        Create a new task instance for a specific task type that is associated with an experiment.

        :param task_definition: The task definition.
        """
        task_id = task_definition.id
        experiment_id = task_definition.experiment_id
        task_type = task_definition.type

        if await self._tasks.exists(experiment_id=experiment_id, id=task_id):
            raise EosTaskExistsError(f"Cannot create task '{task_id}' as a task with that ID already exists.")

        task_spec = self._configuration_manager.task_specs.get_spec_by_type(task_type)
        if not task_spec:
            raise EosTaskStateError(f"Task type '{task_type}' does not exist.")

        task = Task.from_definition(task_definition)
        await self._tasks.create(task.model_dump())

    async def delete_task(self, experiment_id: str, task_id: str) -> None:
        """
        Delete an experiment task instance.
        """
        await self._validate_task_exists(experiment_id, task_id)

        await asyncio.gather(
            self._experiments.delete_running_task(experiment_id, task_id),
            self._tasks.delete_one(experiment_id=experiment_id, id=task_id),
        )

        log.info(f"Deleted task '{task_id}' from experiment '{experiment_id}'.")

    async def start_task(self, experiment_id: str, task_id: str) -> None:
        """
        Add a task to the running tasks list and update its status to running.
        """
        await self._validate_task_exists(experiment_id, task_id)

        await asyncio.gather(
            self._experiments.add_running_task(experiment_id, task_id),
            self._set_task_status(experiment_id, task_id, TaskStatus.RUNNING),
        )

    async def complete_task(self, experiment_id: str, task_id: str) -> None:
        """
        Remove a task from the running tasks list and add it to the completed tasks list.
        """
        await self._validate_task_exists(experiment_id, task_id)

        await asyncio.gather(
            self._experiments.move_task_queue(experiment_id, task_id, "running_tasks", "completed_tasks"),
            self._set_task_status(experiment_id, task_id, TaskStatus.COMPLETED),
        )

    async def fail_task(self, experiment_id: str, task_id: str) -> None:
        """
        Remove a task from the running tasks list and do not add it to the executed tasks list. Update the task status
        to failed.
        """
        await self._validate_task_exists(experiment_id, task_id)

        await asyncio.gather(
            self._experiments.delete_running_task(experiment_id, task_id),
            self._set_task_status(experiment_id, task_id, TaskStatus.FAILED),
        )

    async def cancel_task(self, experiment_id: str, task_id: str) -> None:
        """
        Remove a task from the running tasks list and do not add it to the executed tasks list. Update the task status
        to be cancelled.
        """
        await self._validate_task_exists(experiment_id, task_id)

        await asyncio.gather(
            self._experiments.delete_running_task(experiment_id, task_id),
            self._set_task_status(experiment_id, task_id, TaskStatus.CANCELLED),
        )
        log.warning(f"EXP '{experiment_id}' - Cancelled task '{task_id}'.")

    async def get_task(self, experiment_id: str, task_id: str) -> Task | None:
        """
        Get a task by its ID and experiment ID.
        """
        task = await self._tasks.get_one(experiment_id=experiment_id, id=task_id)
        return Task(**task) if task else None

    async def get_tasks(self, **query: dict[str, Any]) -> list[Task]:
        """
        Query tasks with arbitrary parameters.

        :param query: Dictionary of query parameters.
        """
        tasks = await self._tasks.get_all(**query)
        return [Task(**task) for task in tasks]

    async def add_task_output(self, experiment_id: str, task_id: str, task_output: TaskOutput) -> None:
        """
        Add the output of a task to the database.
        """
        await self._tasks.update_one({"output": task_output.model_dump()}, experiment_id=experiment_id, id=task_id)

    async def get_task_output(self, experiment_id: str, task_id: str) -> TaskOutput | None:
        """
        Get the output of a task by its ID and experiment ID.
        """
        result = await self._tasks.get_one(experiment_id=experiment_id, id=task_id)
        if not result:
            return None

        task = Task(**result)
        if not task.output:
            return None

        return task.output

    def add_task_output_file(self, experiment_id: str, task_id: str, file_name: str, file_data: bytes) -> None:
        """
        Add a file output from a task to the file database.
        """
        path = f"{experiment_id}/{task_id}/{file_name}"
        self._file_db_interface.store_file(path, file_data)

    def get_task_output_file(self, experiment_id: str, task_id: str, file_name: str) -> bytes:
        """
        Get a file output from a task from the file database.
        """
        path = f"{experiment_id}/{task_id}/{file_name}"
        return self._file_db_interface.get_file(path)

    def stream_task_output_file(
        self, experiment_id: str, task_id: str, file_name: str, chunk_size: int = 3 * 1024 * 1024
    ) -> AsyncIterable[bytes]:
        """
        Stream a file output from a task from the file database.
        """
        path = f"{experiment_id}/{task_id}/{file_name}"
        return self._file_db_interface.stream_file(path, chunk_size)

    def list_task_output_files(self, experiment_id: str, task_id: str) -> list[str]:
        """
        List all file outputs from a task in the file database.
        """
        prefix = f"{experiment_id}/{task_id}/"
        return self._file_db_interface.list_files(prefix)

    def delete_task_output_file(self, experiment_id: str, task_id: str, file_name: str) -> None:
        """
        Delete a file output from a task in the file database.
        """
        path = f"{experiment_id}/{task_id}/{file_name}"
        self._file_db_interface.delete_file(path)

    async def _set_task_status(self, experiment_id: str, task_id: str, new_status: TaskStatus) -> None:
        """
        Update the status of a task.
        """
        await self._validate_task_exists(experiment_id, task_id)

        update_fields = {"status": new_status.value}
        if new_status == TaskStatus.RUNNING:
            update_fields["start_time"] = datetime.now(tz=timezone.utc)
        elif new_status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            update_fields["end_time"] = datetime.now(tz=timezone.utc)

        await self._tasks.update_one(update_fields, experiment_id=experiment_id, id=task_id)

    async def _validate_task_exists(self, experiment_id: str, task_id: str) -> None:
        """
        Check if a task exists in an experiment.
        """
        if not await self._tasks.exists(experiment_id=experiment_id, id=task_id):
            raise EosTaskStateError(f"Task '{task_id}' does not exist in experiment '{experiment_id}'.")
