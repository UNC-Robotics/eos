from collections.abc import AsyncGenerator, Callable

from litestar.di import Provide

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator


async def provide_db_session(orchestrator: Orchestrator) -> AsyncGenerator[AsyncDbSession, None]:
    """Provide a database session as a dependency."""
    async with orchestrator.db_interface.get_async_session() as db:
        yield db


def get_orchestrator_provider(orchestrator: Orchestrator) -> Callable[[], Orchestrator]:
    """Create a provider function for the orchestrator."""
    return lambda: orchestrator


def get_common_dependencies(orchestrator: Orchestrator) -> dict:
    """Get common dependencies for controllers."""
    return {
        "db": Provide(provide_db_session),
        "orchestrator": Provide(get_orchestrator_provider(orchestrator)),
    }
