from litestar import get, Controller


class HealthController(Controller):
    """Controller for health check endpoint."""

    path = "/health"

    @get("/")
    async def health_check(self) -> dict[str, str]:
        """Return health status of the orchestrator."""
        return {"status": "ok"}
