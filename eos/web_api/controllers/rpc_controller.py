from typing import Any, ClassVar

from litestar import post, Controller
from pydantic import BaseModel

from eos.auth.authorization import require_lab_admin
from eos.orchestration.orchestrator import Orchestrator


class DeviceRPCRequest(BaseModel):
    function_name: str
    parameters: dict[str, Any] = {}


class RPCController(Controller):
    """Controller for RPC endpoints."""

    path = "/rpc"
    guards: ClassVar = [require_lab_admin("lab_id")]

    @post("/{lab_id:str}/{device_id:str}/{function_name:str}")
    async def call_device_function(
        self,
        lab_id: str,
        device_id: str,
        function_name: str,
        orchestrator: Orchestrator,
        data: dict[str, Any] | None = None,
    ) -> Any:
        """Call any device function via RPC with parameters in JSON format."""
        parameters = data or {}
        return await orchestrator.labs.call_device_function(lab_id, device_id, function_name, parameters)
