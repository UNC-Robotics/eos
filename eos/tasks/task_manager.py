from collections.abc import AsyncIterable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update, delete, exists

from eos.configuration.configuration_manager import ConfigurationManager
from eos.experiments.entities.experiment import ExperimentModel
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.database.file_db_interface import FileDbInterface
from eos.tasks.entities.task import Task, TaskStatus, TaskDefinition, TaskModel
from eos.tasks.exceptions import EosTaskStateError, EosTaskExistsError
from eos.utils.di.di_container import inject_all


class TaskManager:
    """
    Manages the state of all tasks in EOS.
    """

    @inject_all
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        file_db_interface: FileDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._file_db_interface = file_db_interface

        log.debug("Task manager initialized.")

    async def _check_task_exists(self, db: AsyncDbSession, experiment_id: str, task_id: str) -> bool:
        """
        Check if a task exists.

        :param db: Database session
        :param experiment_id: The ID of the experiment
        :param task_id: The ID of the task
        :return: True if task exists, False otherwise
        """
        result = await db.execute(
            select(exists().where(TaskModel.experiment_id == experiment_id, TaskModel.id == task_id))
        )
        return bool(result.scalar_one_or_none())

    async def create_task(self, db: AsyncDbSession, task_definition: TaskDefinition) -> None:
        """Create a new task instance for a specific task type that is associated with an experiment."""
        if await self._check_task_exists(db, task_definition.experiment_id, task_definition.id):
            raise EosTaskExistsError(f"Cannot create task '{task_definition.id}' as it already exists.")

        task_spec = self._configuration_manager.task_specs.get_spec_by_type(task_definition.type)
        if not task_spec:
            raise EosTaskStateError(f"Task type '{task_definition.type}' does not exist.")

        task = Task.from_definition(task_definition)
        task_model = TaskModel(
            experiment_id=task.experiment_id,
            id=task.id,
            type=task.type,
            devices=[device.model_dump() for device in task.devices],
            input_parameters=task.input_parameters,
            input_containers={k: v.model_dump() for k, v in (task.input_containers or {}).items()},
            priority=task.priority,
            resource_allocation_timeout=task.resource_allocation_timeout,
            meta=task.meta,
            status=task.status,
            created_at=task.created_at,
        )

        db.add(task_model)
        await db.flush()

    async def _validate_task_exists(self, db: AsyncDbSession, experiment_id: str, task_id: str) -> None:
        """Check if a task exists."""
        if not await self._check_task_exists(db, experiment_id, task_id):
            raise EosTaskStateError(f"Task '{task_id}' in experiment '{experiment_id}' does not exist.")

    async def delete_task(self, db: AsyncDbSession, experiment_id: str, task_id: str) -> None:
        """Delete an experiment task instance."""
        await db.execute(delete(TaskModel).where(TaskModel.experiment_id == experiment_id, TaskModel.id == task_id))
        log.info(f"Deleted task '{task_id}' from experiment '{experiment_id}'.")

    async def _update_experiment_tasks(
        self,
        db: AsyncDbSession,
        experiment_id: str,
        task_id: str,
        add_to: list[str] | None = None,
        remove_from: list[str] | None = None,
    ) -> None:
        """
        Update experiment task lists.

        :param db: Database session
        :param experiment_id: The ID of the experiment
        :param task_id: The ID of the task
        :param add_to: List of fields to add the task ID to
        :param remove_from: List of fields to remove the task ID from
        """
        if experiment_id == "on_demand":
            return

        update_values = {}

        # First get the current state of the experiment
        result = await db.execute(select(ExperimentModel).where(ExperimentModel.id == experiment_id))
        experiment = result.scalar_one_or_none()
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        if remove_from:
            for field in remove_from:
                current_array = getattr(experiment, field, [])
                update_values[field] = [x for x in current_array if x != task_id]

        if add_to:
            for field in add_to:
                current_array = getattr(experiment, field, [])
                if task_id not in current_array:
                    update_values[field] = [*current_array, task_id]

        if update_values:
            await db.execute(update(ExperimentModel).where(ExperimentModel.id == experiment_id).values(update_values))

    async def start_task(self, db: AsyncDbSession, experiment_id: str | None, task_id: str) -> None:
        """Add a task to the running tasks list and update its status to running."""
        await self._validate_task_exists(db, experiment_id, task_id)
        await self._set_task_status(db, experiment_id, task_id, TaskStatus.RUNNING)
        if experiment_id:
            await self._update_experiment_tasks(db, experiment_id, task_id, add_to=["running_tasks"])

    async def complete_task(self, db: AsyncDbSession, experiment_id: str | None, task_id: str) -> None:
        """Update task status to completed and move task from running to completed queue."""
        await self._validate_task_exists(db, experiment_id, task_id)
        await self._set_task_status(db, experiment_id, task_id, TaskStatus.COMPLETED)
        if experiment_id:
            await self._update_experiment_tasks(
                db, experiment_id, task_id, add_to=["completed_tasks"], remove_from=["running_tasks"]
            )

    async def fail_task(self, db: AsyncDbSession, experiment_id: str | None, task_id: str) -> None:
        """Update task status to failed and remove from running queue."""
        await self._validate_task_exists(db, experiment_id, task_id)
        await self._set_task_status(db, experiment_id, task_id, TaskStatus.FAILED)
        if experiment_id:
            await self._update_experiment_tasks(db, experiment_id, task_id, remove_from=["running_tasks"])

    async def cancel_task(self, db: AsyncDbSession, experiment_id: str | None, task_id: str) -> None:
        """Update task status to cancelled and remove from running queue."""
        await self._validate_task_exists(db, experiment_id, task_id)
        await self._set_task_status(db, experiment_id, task_id, TaskStatus.CANCELLED)
        if experiment_id:
            await self._update_experiment_tasks(db, experiment_id, task_id, remove_from=["running_tasks"])
        log.warning(f"EXP '{experiment_id}' - Cancelled task '{task_id}'.")

    async def get_task(self, db: AsyncDbSession, experiment_id: str | None, task_id: str) -> Task | None:
        """Get a task by its ID and experiment ID."""
        result = await db.execute(
            select(TaskModel).where(TaskModel.experiment_id == experiment_id, TaskModel.id == task_id)
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
        experiment_id: str | None,
        task_id: str,
        output_parameters: dict[str, Any] | None = None,
        output_containers: dict[str, Any] | None = None,
        output_file_names: list[str] | None = None,
    ) -> None:
        """Add the output of a task to the database."""
        await db.execute(
            update(TaskModel)
            .where(TaskModel.experiment_id == experiment_id, TaskModel.id == task_id)
            .values(
                output_parameters=output_parameters,
                output_containers={k: v.model_dump() for k, v in (output_containers or {}).items()},
                output_file_names=output_file_names,
                end_time=datetime.now(timezone.utc),
            )
        )

    def _get_task_output_file_path(self, experiment_id: str | None, task_id: str, file_name: str) -> str:
        """Generate consistent file paths for task outputs."""
        return f"{experiment_id if experiment_id is not None else 'on_demand'}/{task_id}/{file_name}"

    def add_task_output_file(self, experiment_id: str | None, task_id: str, file_name: str, file_data: bytes) -> None:
        """Add a file output from a task to the file database."""
        path = self._get_task_output_file_path(experiment_id, task_id, file_name)
        self._file_db_interface.store_file(path, file_data)

    def get_task_output_file(self, experiment_id: str, task_id: str, file_name: str) -> bytes:
        """Get a file output from a task from the file database."""
        path = self._get_task_output_file_path(experiment_id, task_id, file_name)
        return self._file_db_interface.get_file(path)

    def stream_task_output_file(
        self, experiment_id: str, task_id: str, file_name: str, chunk_size: int = 3 * 1024 * 1024
    ) -> AsyncIterable[bytes]:
        """Stream a file output from a task from the file database."""
        path = self._get_task_output_file_path(experiment_id, task_id, file_name)
        return self._file_db_interface.stream_file(path, chunk_size)

    def list_task_output_files(self, experiment_id: str, task_id: str) -> list[str]:
        """List all file outputs from a task in the file database."""
        prefix = self._get_task_output_file_path(experiment_id, task_id, "")
        return self._file_db_interface.list_files(prefix)

    def delete_task_output_file(self, experiment_id: str, task_id: str, file_name: str) -> None:
        """Delete a file output from a task in the file database."""
        path = self._get_task_output_file_path(experiment_id, task_id, file_name)
        self._file_db_interface.delete_file(path)

    async def _set_task_status(
        self, db: AsyncDbSession, experiment_id: str, task_id: str, new_status: TaskStatus
    ) -> None:
        """Update the status of a task."""
        update_fields = {"status": new_status}
        now = datetime.now(timezone.utc)

        if new_status == TaskStatus.RUNNING:
            update_fields["start_time"] = now
            update_fields["end_time"] = None
        elif new_status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            update_fields["end_time"] = now

        await db.execute(
            update(TaskModel)
            .where(TaskModel.experiment_id == experiment_id, TaskModel.id == task_id)
            .values(**update_fields)
        )
