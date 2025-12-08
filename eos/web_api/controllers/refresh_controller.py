from litestar import Controller, post

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator


class RefreshController(Controller):
    """Controller for refreshing package discovery and specifications."""

    path = "/refresh"

    @post("/packages")
    async def refresh_packages(self, db: AsyncDbSession, orchestrator: Orchestrator) -> dict[str, str | int]:
        """
        Re-discover packages from the filesystem and sync specifications to the database.
        This allows the system to detect new or deleted entities (labs, experiments, tasks, devices).
        """
        try:
            package_count = await orchestrator.loading.refresh_packages(db)

            return {
                "message": "Packages refreshed successfully",
                "package_count": package_count,
            }

        except Exception:
            raise
