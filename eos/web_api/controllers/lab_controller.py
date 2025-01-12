from litestar import Controller, put, get, Response
from litestar.status_codes import HTTP_200_OK

from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.entities import LabTypes
from eos.web_api.exception_handling import handle_exceptions


class LabController(Controller):
    path = "/labs"

    @get("/devices")
    @handle_exceptions("Failed to get lab devices")
    async def get_lab_devices(
        self, lab_types: list[str] | None, task_type: str | None, orchestrator: Orchestrator
    ) -> Response:
        lab_devices = await orchestrator.labs.get_lab_devices(lab_types, task_type)

        # Convert LabDeviceConfig objects to plain dictionaries
        dict_lab_devices = {}
        for lab_type, devices in lab_devices.items():
            dict_lab_devices[lab_type] = {name: device.model_dump() for name, device in devices.items()}

        return Response(content=dict_lab_devices, status_code=HTTP_200_OK)

    @put("/update_loaded")
    @handle_exceptions("Failed to update loaded labs")
    async def update_loaded_labs(self, data: LabTypes, orchestrator: Orchestrator) -> Response:
        async with orchestrator.db_interface.get_async_session() as db:
            await orchestrator.loading.update_loaded_labs(db, set(data.lab_types))
        return Response(content=None, status_code=HTTP_200_OK)

    @put("/reload")
    @handle_exceptions("Failed to reload labs")
    async def reload_labs(self, data: LabTypes, orchestrator: Orchestrator) -> Response:
        async with orchestrator.db_interface.get_async_session() as db:
            await orchestrator.loading.reload_labs(db, set(data.lab_types))
        return Response(content=None, status_code=HTTP_200_OK)

    @get("/loaded")
    @handle_exceptions("Failed to get loaded labs")
    async def get_loaded_labs(self, orchestrator: Orchestrator) -> Response:
        lab_loaded_statuses = await orchestrator.loading.list_loaded_labs()
        return Response(content=lab_loaded_statuses, status_code=HTTP_200_OK)
