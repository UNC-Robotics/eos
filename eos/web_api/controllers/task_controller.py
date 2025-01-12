from litestar import Controller, Response, get
from litestar.handlers import post
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED

from eos.orchestration.orchestrator import Orchestrator
from eos.tasks.entities.task import TaskDefinition
from eos.web_api.entities import TaskTypesResponse
from eos.web_api.exception_handling import handle_exceptions


class TaskController(Controller):
    path = "/tasks"

    @get("/{experiment_id:str}/{task_id:str}")
    @handle_exceptions("Failed to get task")
    async def get_task(self, experiment_id: str, task_id: str, orchestrator: Orchestrator) -> Response:
        async with orchestrator.db_interface.get_async_session() as db:
            task = await orchestrator.tasks.get_task(db, experiment_id, task_id)
        return Response(content=task.model_dump_json(), status_code=HTTP_200_OK)

    @post("/submit")
    @handle_exceptions("Failed to submit task")
    async def submit_task(self, data: TaskDefinition, orchestrator: Orchestrator) -> Response:
        async with orchestrator.db_interface.get_async_session() as db:
            await orchestrator.tasks.submit_task(db, data)
        return Response(content=None, status_code=HTTP_201_CREATED)

    @post("/{task_id:str}/cancel")
    @handle_exceptions("Failed to cancel task")
    async def cancel_task(self, task_id: str, orchestrator: Orchestrator) -> Response:
        async with orchestrator.db_interface.get_async_session() as db:
            await orchestrator.tasks.cancel_task(db, task_id)
        return Response(content=None, status_code=HTTP_200_OK)

    @get("/types")
    @handle_exceptions("Failed to get task types")
    async def get_task_types(self, orchestrator: Orchestrator) -> TaskTypesResponse:
        task_types = await orchestrator.tasks.get_task_types()
        return TaskTypesResponse(task_types=task_types)

    @get("/{task_type:str}/spec")
    @handle_exceptions("Failed to get task spec")
    async def get_task_spec(self, task_type: str, orchestrator: Orchestrator) -> Response:
        task_spec = await orchestrator.tasks.get_task_spec(task_type)
        return Response(content=task_spec, status_code=HTTP_200_OK)
