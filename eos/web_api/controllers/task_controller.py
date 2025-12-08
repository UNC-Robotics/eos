from typing import Any

from litestar import get, post, Controller
from pydantic import BaseModel

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator
from eos.tasks.entities.task import TaskDefinition, Task
from eos.web_api.exception_handling import APIError


class TaskTypesResponse(BaseModel):
    task_types: list[str]


class ReloadTaskPluginsRequest(BaseModel):
    task_types: list[str]


class TaskController(Controller):
    """Controller for task-related endpoints."""

    path = "/tasks"

    @get("/{experiment_name:str}/{task_name:str}")
    async def get_task(
        self, experiment_name: str, task_name: str, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> Task:
        """Get a task by name."""
        task = await orchestrator.tasks.get_task(db, experiment_name, task_name)
        if not task:
            raise APIError(status_code=404, detail="Task not found")
        return task

    @post("/")
    async def submit_task(self, data: TaskDefinition, db: AsyncDbSession, orchestrator: Orchestrator) -> dict[str, str]:
        """Submit a new task for execution."""
        await orchestrator.tasks.submit_task(db, data)
        return {"message": "Task submitted"}

    @post("/{task_name:str}/cancel")
    async def cancel_task(
        self, task_name: str, orchestrator: Orchestrator, experiment_name: str | None = None
    ) -> dict[str, str]:
        """Cancel a running task. For experiment tasks, provide the experiment_name query parameter."""
        await orchestrator.tasks.cancel_task(task_name, experiment_name)
        return {"message": "Task cancellation requested"}

    @get("/types")
    async def get_task_types(self, orchestrator: Orchestrator) -> TaskTypesResponse:
        """Get all available task types."""
        task_types = await orchestrator.tasks.get_task_types()
        return TaskTypesResponse(task_types=task_types)

    @get("/{task_type:str}/spec")
    async def get_task_spec(self, task_type: str, orchestrator: Orchestrator) -> dict[str, Any]:
        """Get specification for a task type."""
        task_spec = await orchestrator.tasks.get_task_spec(task_type)
        if not task_spec:
            raise APIError(status_code=404, detail=f"Task type '{task_type}' not found")
        return task_spec.model_dump()

    @post("/reload")
    async def reload_tasks(
        self, data: ReloadTaskPluginsRequest, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Reload specified task plugins."""
        await orchestrator.loading.reload_task_plugins(db, set(data.task_types))
        return {"message": "Task plugins reloaded"}
