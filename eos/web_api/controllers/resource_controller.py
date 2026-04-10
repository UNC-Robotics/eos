from litestar import get, post, Controller
from pydantic import BaseModel

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.utils.di.di_deps import get_resource_manager


class ResetResourcesRequest(BaseModel):
    resource_names: list[str]


class ResourceController(Controller):
    """Controller for resource-related endpoints."""

    path = "/resources"

    @get("/")
    async def get_resources(self, db: AsyncDbSession) -> list[dict]:
        """Get all resources."""
        resources = await get_resource_manager().get_resources(db)
        return [r.model_dump() for r in resources]

    @post("/reset")
    async def reset_resources(self, data: ResetResourcesRequest, db: AsyncDbSession) -> list[dict]:
        """Reset resources to their default metadata from lab configuration."""
        resource_manager = get_resource_manager()

        reset = []
        for name in data.resource_names:
            default = resource_manager.get_default_resource(name)
            if default:
                await resource_manager.update_resource(db, default)
                reset.append(default)

        await db.commit()
        return [r.model_dump() for r in reset]
