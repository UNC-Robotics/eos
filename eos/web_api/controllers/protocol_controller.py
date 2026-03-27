import re

import yaml as pyyaml
from litestar import get, post, Controller
from pydantic import BaseModel
from sqlalchemy import select

from eos.configuration.entities.definition import DefinitionModel
from eos.configuration.entities.protocol_def import ProtocolDef
from eos.configuration.entities.lab_def import LabDef
from eos.configuration.validation import ProtocolValidator
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.protocols.entities.protocol_run import ProtocolRunSubmission, ProtocolRun
from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.exception_handling import APIError

# Pattern to extract task names from validation error messages
_TASK_NAME_PATTERN = re.compile(r"[Tt]ask '([^']+)'")


def _parse_validation_errors(error_message: str) -> list[dict]:
    """Parse a multi-line validation error into structured per-task errors."""
    errors = []
    for raw_line in error_message.strip().split("\n"):
        cleaned = raw_line.strip().lstrip("- ")
        if not cleaned:
            continue
        match = _TASK_NAME_PATTERN.search(cleaned)
        errors.append({"task": match.group(1) if match else None, "message": cleaned})
    return errors or [{"task": None, "message": error_message}]


class ProtocolTypes(BaseModel):
    protocol_types: list[str]


class ProtocolTypesResponse(BaseModel):
    protocol_types: list[str]


class ProtocolValidationRequest(BaseModel):
    protocol_yaml: str


class ProtocolController(Controller):
    """Controller for protocol-related endpoints."""

    path = "/protocols"

    @post("/")
    async def submit_protocol_run(
        self, data: ProtocolRunSubmission, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Submit a new protocol run for execution."""
        await orchestrator.protocols.submit_protocol_run(db, data)
        return {"message": "ProtocolRun submitted"}

    @post("/{protocol_run_name:str}/cancel")
    async def cancel_protocol_run(self, protocol_run_name: str, orchestrator: Orchestrator) -> dict[str, str]:
        """Cancel a running protocol run (standalone or part of a campaign)."""
        # First try to cancel as a standalone protocol run
        if protocol_run_name in orchestrator.protocols.submitted_protocol_runs:
            await orchestrator.protocols.cancel_protocol_run(protocol_run_name)
            return {"message": "ProtocolRun cancellation requested"}

        # Try to cancel as a campaign protocol run (queues for cancellation in campaign's main loop)
        queued = await orchestrator.campaigns.cancel_campaign_protocol_run(protocol_run_name)
        if queued:
            return {"message": "Campaign protocol run cancellation queued"}

        raise APIError(status_code=404, detail=f"ProtocolRun '{protocol_run_name}' not found in running protocols")

    @get("/{protocol_run_name:str}")
    async def get_protocol_run(
        self, protocol_run_name: str, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> ProtocolRun:
        """Get a protocol run by name."""
        protocol_run = await orchestrator.protocols.get_protocol_run(db, protocol_run_name)

        if protocol_run is None:
            raise APIError(status_code=404, detail="ProtocolRun not found")

        return protocol_run

    @get("/types")
    async def get_protocol_types(self, orchestrator: Orchestrator) -> dict[str, bool]:
        """List protocol types."""
        return await orchestrator.loading.list_protocols()

    @post("/load")
    async def load_protocols(
        self, data: ProtocolTypes, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Load protocol configurations."""
        await orchestrator.loading.load_protocols(db, set(data.protocol_types))
        return {"message": "Protocol configurations loaded"}

    @post("/unload")
    async def unload_protocols(
        self, data: ProtocolTypes, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Unload protocol configurations."""
        await orchestrator.loading.unload_protocols(db, set(data.protocol_types))
        return {"message": "Protocol configurations unloaded"}

    @post("/reload")
    async def reload_protocols(
        self, data: ProtocolTypes, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Reload protocol configurations."""
        await orchestrator.loading.reload_protocols(db, set(data.protocol_types))
        return {"message": "Protocol configurations reloaded"}

    @post("/validate")
    async def validate_protocol_yaml(self, data: ProtocolValidationRequest, db: AsyncDbSession) -> dict:
        """Validate protocol YAML against lab and task specs.

        Returns structured errors with per-task attribution when possible.
        """
        # Parse YAML
        try:
            raw = pyyaml.safe_load(data.protocol_yaml)
            protocol_def = ProtocolDef.model_validate(raw)
        except Exception as e:
            return {"valid": False, "errors": [{"task": None, "message": f"YAML parse error: {e}"}]}

        lab_names = list(protocol_def.labs)
        result = await db.execute(
            select(DefinitionModel).where(
                DefinitionModel.type == "lab",
                DefinitionModel.name.in_(lab_names),
            )
        )
        lab_defs = {defn.name: defn for defn in result.scalars()}
        missing_labs = [name for name in lab_names if name not in lab_defs]

        if missing_labs:
            return {
                "valid": False,
                "errors": [{"task": None, "message": f"Unknown labs: {missing_labs}"}],
            }

        labs = [LabDef.model_validate(lab_defs[name].data) for name in lab_names]

        # Validate using the authoritative ProtocolValidator
        try:
            ProtocolValidator(protocol_def, labs).validate()
            return {"valid": True, "errors": []}
        except Exception as e:
            return {"valid": False, "errors": _parse_validation_errors(str(e))}
