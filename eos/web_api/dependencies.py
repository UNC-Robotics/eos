from collections.abc import AsyncGenerator, Callable

from litestar import Request
from litestar.di import Provide

from eos.auth.authorization import DEV_SUPERUSER, is_auth_disabled
from eos.auth.entities.user_role import AuthenticatedUser
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator


async def provide_db_session(orchestrator: Orchestrator) -> AsyncGenerator[AsyncDbSession, None]:
    """Provide a database session as a dependency."""
    async with orchestrator.db_interface.get_async_session() as db:
        yield db


def get_orchestrator_provider(orchestrator: Orchestrator) -> Callable[[], Orchestrator]:
    """Create a provider function for the orchestrator."""
    return lambda: orchestrator


def provide_current_user(request: Request) -> AuthenticatedUser:
    """Provide the authenticated user, or a dev superuser when auth is disabled."""
    if is_auth_disabled(request):
        return DEV_SUPERUSER
    return request.user


def get_common_dependencies(orchestrator: Orchestrator) -> dict:
    """Get common dependencies for controllers."""
    return {
        "db": Provide(provide_db_session),
        "orchestrator": Provide(get_orchestrator_provider(orchestrator)),
        "user": Provide(provide_current_user, sync_to_thread=False),
    }
