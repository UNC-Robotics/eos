from typing import Any

from litestar import get, Controller

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.exception_handling import APIError


class DefinitionController(Controller):
    """Controller for definition-related endpoints."""

    path = "/defs"

    @get("/")
    async def list_definitions(
        self, db: AsyncDbSession, orchestrator: Orchestrator, def_type: str | None = None
    ) -> list[dict[str, Any]]:
        """List all definitions, optionally filtered by type.

        :param def_type: Optional type filter (task, device, lab, experiment)
        """
        definitions = await orchestrator.definitions.get_definitions(db, def_type)
        return [defn.model_dump() for defn in definitions]

    @get("/{def_type:str}")
    async def list_definitions_by_type(
        self, def_type: str, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> list[dict[str, Any]]:
        """List all definitions of a specific type.

        :param def_type: Definition type (task, device, lab, experiment)
        """
        definitions = await orchestrator.definitions.get_definitions(db, def_type)
        return [defn.model_dump() for defn in definitions]

    @get("/{def_type:str}/{name:str}")
    async def get_definition(
        self, def_type: str, name: str, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, Any]:
        """Get a single definition by type and name.

        :param def_type: Definition type (task, device, lab, experiment)
        :param name: Definition name
        """
        definition = await orchestrator.definitions.get_definition(db, def_type, name)

        if definition is None:
            raise APIError(status_code=404, detail=f"Definition '{def_type}/{name}' not found")

        return definition.model_dump()
