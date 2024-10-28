from litestar import Controller, Response, get
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from litestar.handlers import post
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED, HTTP_404_NOT_FOUND

from eos.tasks.entities.task import TaskDefinition
from eos.web_api.common.entities import TaskTypesResponse
from eos.web_api.public.exception_handling import handle_exceptions


class TaskController(Controller):
    path = "/tasks"

    @get("/{experiment_id:str}/{task_id:str}")
    @handle_exceptions("Failed to get task")
    async def get_task(self, experiment_id: str, task_id: str, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.get(f"/api/tasks/{experiment_id}/{task_id}") as response:
            if response.status == HTTP_200_OK:
                task = await response.json()
                return Response(content=task, status_code=HTTP_200_OK)
            if response.status == HTTP_404_NOT_FOUND:
                return Response(content={"error": "Task not found"}, status_code=HTTP_404_NOT_FOUND)

            raise HTTPException(status_code=response.status, detail="Error fetching task")

    @post("/submit")
    @handle_exceptions("Failed to submit task")
    async def submit_task(self, data: TaskDefinition, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.post("/api/tasks/submit", json=data.model_dump()) as response:
            if response.status == HTTP_201_CREATED:
                result = await response.json()
                return Response(content=result, status_code=HTTP_201_CREATED)

            raise HTTPException(status_code=response.status, detail="Error submitting task")

    @post("/{task_id:str}/cancel")
    @handle_exceptions("Failed to cancel task")
    async def cancel_task(self, task_id: str, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.post(f"/api/tasks/{task_id}/cancel") as response:
            if response.status == HTTP_200_OK:
                return Response(content={"message": "Task cancelled successfully"}, status_code=HTTP_200_OK)
            if response.status == HTTP_404_NOT_FOUND:
                return Response(content={"error": "Task not found"}, status_code=HTTP_404_NOT_FOUND)

            raise HTTPException(status_code=response.status, detail="Error cancelling task")

    @get("/types")
    @handle_exceptions("Failed to get task types")
    async def get_task_types(self, state: State) -> TaskTypesResponse:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.get("/api/tasks/types") as response:
            if response.status == HTTP_200_OK:
                return TaskTypesResponse(**await response.json())

            raise HTTPException(status_code=response.status, detail="Error fetching task types")

    @get("/{task_type:str}/spec")
    @handle_exceptions("Failed to get task spec")
    async def get_task_spec(self, task_type: str, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.get(f"/api/tasks/{task_type}/spec") as response:
            if response.status == HTTP_200_OK:
                task_spec = await response.json()
                return Response(content=task_spec, status_code=HTTP_200_OK)
            if response.status == HTTP_404_NOT_FOUND:
                return Response(content={"error": "Task specification not found"}, status_code=HTTP_404_NOT_FOUND)

            raise HTTPException(status_code=response.status, detail="Error fetching task specification")
