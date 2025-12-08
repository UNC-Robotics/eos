from collections.abc import AsyncIterable
from datetime import datetime, UTC
from typing import Any

from sqlalchemy import select, update, delete, exists

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.database.file_db_interface import FileDbInterface
from eos.tasks.entities.task import Task, TaskStatus, TaskDefinition, TaskModel
from eos.tasks.exceptions import EosTaskStateError, EosTaskExistsError
from eos.utils.di.di_container import inject


class TaskManager:
    """
    Manages the state of all tasks in EOS.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        file_db_interface: FileDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._file_db_interface = file_db_interface

        log.debug("Task manager initialized.")

    async def _check_task_exists(self, db: AsyncDbSession, experiment_name: str, task_name: str) -> bool:
        """
        Check if a task exists.

        :param db: Database session
        :param experiment_name: The name of the experiment
        :param task_name: The name of the task
        :return: True if task exists, False otherwise
        """
        result = await db.execute(
            select(exists().where(TaskModel.experiment_name == experiment_name, TaskModel.name == task_name))
        )
        return bool(result.scalar_one_or_none())

    async def create_task(self, db: AsyncDbSession, task_definition: TaskDefinition) -> None:
        """Create a new task instance for a specific task type that is associated with an experiment."""
        if await self._check_task_exists(db, task_definition.experiment_name, task_definition.name):
            raise EosTaskExistsError(f"Cannot create task '{task_definition.name}' as it already exists.")

        task_spec = self._configuration_manager.task_specs.get_spec_by_type(task_definition.type)
        if not task_spec:
            raise EosTaskStateError(f"Task type '{task_definition.type}' does not exist.")

        task = Task.from_definition(task_definition)
        task_model = TaskModel(
            experiment_name=task.experiment_name,
            name=task.name,
            type=task.type,
            devices={k: v.model_dump() for k, v in task.devices.items()},
            input_parameters=task.input_parameters,
            input_resources={k: v.model_dump() for k, v in (task.input_resources or {}).items()},
            priority=task.priority,
            allocation_timeout=task.allocation_timeout,
            meta=task.meta,
            status=task.status,
            created_at=task.created_at,
        )

        db.add(task_model)
        await db.flush()

    async def _validate_task_exists(self, db: AsyncDbSession, experiment_name: str, task_name: str) -> None:
        """Check if a task exists."""
        if not await self._check_task_exists(db, experiment_name, task_name):
            raise EosTaskStateError(f"Task '{task_name}' in experiment '{experiment_name}' does not exist.")

    async def delete_task(self, db: AsyncDbSession, experiment_name: str, task_name: str) -> None:
        """Delete an experiment task instance."""
        await db.execute(
            delete(TaskModel).where(TaskModel.experiment_name == experiment_name, TaskModel.name == task_name)
        )
        log.info(f"Deleted task '{task_name}' from experiment '{experiment_name}'.")

    async def start_task(self, db: AsyncDbSession, experiment_name: str | None, task_name: str) -> None:
        """Update task status to running."""
        await self._validate_task_exists(db, experiment_name, task_name)
        await self._set_task_status(db, experiment_name, task_name, TaskStatus.RUNNING)

    async def complete_task(self, db: AsyncDbSession, experiment_name: str | None, task_name: str) -> None:
        """Update task status to completed."""
        await self._validate_task_exists(db, experiment_name, task_name)
        await self._set_task_status(db, experiment_name, task_name, TaskStatus.COMPLETED)

    async def fail_task(self, db: AsyncDbSession, experiment_name: str | None, task_name: str) -> None:
        """Update task status to failed."""
        await self._validate_task_exists(db, experiment_name, task_name)
        await self._set_task_status(db, experiment_name, task_name, TaskStatus.FAILED)

    async def cancel_task(self, db: AsyncDbSession, experiment_name: str | None, task_name: str) -> None:
        """Update task status to cancelled."""
        await self._validate_task_exists(db, experiment_name, task_name)
        await self._set_task_status(db, experiment_name, task_name, TaskStatus.CANCELLED)
        log.warning(f"EXP '{experiment_name}' - Cancelled task '{task_name}'.")

    async def get_task(self, db: AsyncDbSession, experiment_name: str | None, task_name: str) -> Task | None:
        """Get a task by its name and experiment name."""
        result = await db.execute(
            select(TaskModel).where(TaskModel.experiment_name == experiment_name, TaskModel.name == task_name)
        )
        if task_model := result.scalar_one_or_none():
            return Task.model_validate(task_model)
        return None

    async def get_tasks(self, db: AsyncDbSession, **filters: Any) -> list[Task]:
        """
        Query tasks with arbitrary parameters.

        :param db: The database session.
        :param filters: Dictionary of query parameters.
        """
        stmt = select(TaskModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(TaskModel, key) == value)

        result = await db.execute(stmt)
        return [Task.model_validate(task_model) for task_model in result.scalars()]

    async def add_task_output(
        self,
        db: AsyncDbSession,
        experiment_name: str | None,
        task_name: str,
        output_parameters: dict[str, Any] | None = None,
        output_resources: dict[str, Any] | None = None,
        output_file_names: list[str] | None = None,
    ) -> None:
        """Add the output of a task to the database."""
        await db.execute(
            update(TaskModel)
            .where(TaskModel.experiment_name == experiment_name, TaskModel.name == task_name)
            .values(
                output_parameters=output_parameters,
                output_resources={k: v.model_dump() for k, v in (output_resources or {}).items()},
                output_file_names=output_file_names,
                end_time=datetime.now(UTC),
            )
        )

    def _get_task_output_file_path(self, experiment_name: str | None, task_name: str, file_name: str) -> str:
        """Generate consistent file paths for task outputs."""
        return f"{experiment_name if experiment_name is not None else 'on_demand'}/{task_name}/{file_name}"

    def add_task_output_file(
        self, experiment_name: str | None, task_name: str, file_name: str, file_data: bytes
    ) -> None:
        """Add a file output from a task to the file database."""
        path = self._get_task_output_file_path(experiment_name, task_name, file_name)
        self._file_db_interface.store_file(path, file_data)

    def get_task_output_file(self, experiment_name: str, task_name: str, file_name: str) -> bytes:
        """Get a file output from a task from the file database."""
        path = self._get_task_output_file_path(experiment_name, task_name, file_name)
        return self._file_db_interface.get_file(path)

    def stream_task_output_file(
        self, experiment_name: str, task_name: str, file_name: str, chunk_size: int = 3 * 1024 * 1024
    ) -> AsyncIterable[bytes]:
        """Stream a file output from a task from the file database."""
        path = self._get_task_output_file_path(experiment_name, task_name, file_name)
        return self._file_db_interface.stream_file(path, chunk_size)

    def list_task_output_files(self, experiment_name: str, task_name: str) -> list[str]:
        """List all file outputs from a task in the file database."""
        prefix = self._get_task_output_file_path(experiment_name, task_name, "")
        return self._file_db_interface.list_files(prefix)

    def delete_task_output_file(self, experiment_name: str, task_name: str, file_name: str) -> None:
        """Delete a file output from a task in the file database."""
        path = self._get_task_output_file_path(experiment_name, task_name, file_name)
        self._file_db_interface.delete_file(path)

    async def _set_task_status(
        self, db: AsyncDbSession, experiment_name: str, task_name: str, new_status: TaskStatus
    ) -> None:
        """Update the status of a task."""
        update_fields = {"status": new_status}
        now = datetime.now(UTC)

        if new_status == TaskStatus.RUNNING:
            update_fields["start_time"] = now
            update_fields["end_time"] = None
        elif new_status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            update_fields["end_time"] = now

        await db.execute(
            update(TaskModel)
            .where(TaskModel.experiment_name == experiment_name, TaskModel.name == task_name)
            .values(**update_fields)
        )
