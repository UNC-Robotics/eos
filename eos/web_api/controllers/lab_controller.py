from typing import Any

from litestar import get, put, Controller, post, Response
from pydantic import BaseModel

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator


class LabTypes(BaseModel):
    lab_types: list[str]


class DeviceReload(BaseModel):
    device_ids: list[str]


class LabController(Controller):
    """Controller for lab-related endpoints."""

    path = "/labs"

    @get("/")
    async def get_labs(self, orchestrator: Orchestrator) -> dict[str, bool]:
        """Get labs."""
        return await orchestrator.loading.list_labs()

    @get("/{lab_id:str}/device/{device_id:str}/report")
    async def get_device_report(self, lab_id: str, device_id: str, orchestrator: Orchestrator) -> dict[str, Any]:
        """Get a report for a specific device."""
        return await orchestrator.labs.get_device_report(lab_id, device_id)

    @post("/load")
    async def load_labs(self, data: LabTypes, db: AsyncDbSession, orchestrator: Orchestrator) -> Response:
        """Load lab configurations."""
        await orchestrator.loading.load_labs(db, set(data.lab_types))
        return Response(content="OK", status_code=200)

    @post("/unload")
    async def unload_labs(self, data: LabTypes, db: AsyncDbSession, orchestrator: Orchestrator) -> Response:
        """Unload lab configurations."""
        await orchestrator.loading.unload_labs(db, set(data.lab_types))
        return Response(content="OK", status_code=200)

    @put("/reload")
    async def reload_labs(self, data: LabTypes, db: AsyncDbSession, orchestrator: Orchestrator) -> Response:
        """Reload lab configurations."""
        await orchestrator.loading.reload_labs(db, set(data.lab_types))
        return Response(content="OK", status_code=200)

    @put("/{lab_id:str}/devices/reload")
    async def reload_devices(
        self, lab_id: str, data: DeviceReload, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> Response:
        """Reload specific devices in a lab."""
        await orchestrator.loading.reload_devices(db, lab_id, data.device_ids)
        return Response(content="OK", status_code=200)

    @get("/devices")
    async def get_lab_devices(
        self, orchestrator: Orchestrator, lab_types: list[str] | None = None, task_type: str | None = None
    ) -> dict[str, dict[str, Any]]:
        """Get devices for specified labs or task type."""
        lab_devices = await orchestrator.labs.get_lab_devices(lab_types, task_type)

        result = {}
        for lab_type, devices in lab_devices.items():
            result[lab_type] = {name: device.model_dump() for name, device in devices.items()}

        return result
