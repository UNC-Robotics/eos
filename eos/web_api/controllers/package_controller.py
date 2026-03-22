from litestar import get, post, Controller
from pydantic import BaseModel

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator


class PackageNames(BaseModel):
    package_names: list[str]


class PackageController(Controller):
    """Controller for package management endpoints."""

    path = "/packages"

    @get("/")
    async def list_packages(self, orchestrator: Orchestrator) -> dict[str, bool]:
        """List all discovered packages and whether they are active."""
        return await orchestrator.loading.list_packages()

    @post("/load")
    async def load_packages(self, data: PackageNames, db: AsyncDbSession, orchestrator: Orchestrator) -> dict[str, str]:
        """Load packages into the active set."""
        await orchestrator.loading.load_packages(db, set(data.package_names))
        return {"message": "Packages loaded"}

    @post("/unload")
    async def unload_packages(
        self, data: PackageNames, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Unload packages from the active set."""
        await orchestrator.loading.unload_packages(db, set(data.package_names))
        return {"message": "Packages unloaded"}
