from typing import ClassVar

from litestar import get, post, Controller
from pydantic import BaseModel

from eos.auth.authorization import DEV_SUPERUSER, require_role
from eos.auth.entities.user_role import AuthenticatedUser, Role
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator
from eos.tasks.entities.task import TaskSubmission, Task
from eos.web_api.exception_handling import APIError


class TaskTypesResponse(BaseModel):
    task_types: list[str]


class ReloadTaskPluginsRequest(BaseModel):
    task_types: list[str]
    if_unused: bool = False


class ReloadTaskPluginsResponse(BaseModel):
    reloaded: list[str]


class TaskController(Controller):
    """Controller for task-related endpoints."""

    path = "/tasks"
    guards: ClassVar = [require_role(Role.VIEWER)]

    @get("/{protocol_run_name:str}/{task_name:str}")
    async def get_task(
        self, protocol_run_name: str, task_name: str, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> Task:
        """Get a task by name."""
        task = await orchestrator.tasks.get_task(db, protocol_run_name, task_name)
        if not task:
            raise APIError(status_code=404, detail="Task not found")
        return task

    @post("/", guards=[require_role(Role.SUBMITTER)])
    async def submit_task(
        self, data: TaskSubmission, db: AsyncDbSession, orchestrator: Orchestrator, user: AuthenticatedUser
    ) -> dict[str, str]:
        """Submit a new task for execution."""
        if user is not DEV_SUPERUSER:
            data.meta["submitted_by"] = user.sub
        await orchestrator.tasks.submit_task(db, data)
        return {"message": "Task submitted"}

    @post("/{task_name:str}/cancel", guards=[require_role(Role.SUBMITTER)])
    async def cancel_task(
        self, task_name: str, orchestrator: Orchestrator, protocol_run_name: str | None = None
    ) -> dict[str, str]:
        """Cancel a running task. For protocol run tasks, provide the protocol_run_name query parameter."""
        await orchestrator.tasks.cancel_task(task_name, protocol_run_name)
        return {"message": "Task cancellation requested"}

    @get("/types")
    async def get_task_types(self, orchestrator: Orchestrator) -> TaskTypesResponse:
        """Get all available task types."""
        task_types = await orchestrator.tasks.get_task_types()
        return TaskTypesResponse(task_types=task_types)

    @post("/reload", guards=[require_role(Role.LAB_ADMIN)])
    async def reload_tasks(
        self, data: ReloadTaskPluginsRequest, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> ReloadTaskPluginsResponse:
        """Reload specified task plugins."""
        reloaded = await orchestrator.loading.reload_task_plugins(db, set(data.task_types), if_unused=data.if_unused)
        return ReloadTaskPluginsResponse(reloaded=sorted(reloaded))
