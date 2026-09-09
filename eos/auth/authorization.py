from collections.abc import Callable, Coroutine
from typing import Protocol

from litestar.connection import ASGIConnection
from litestar.exceptions import PermissionDeniedException
from litestar.handlers.base import BaseRouteHandler
from sqlalchemy import select

from eos.auth.entities.user_role import AuthenticatedUser, Role, UserRoleModel
from eos.database.abstract_sql_db_interface import AsyncDbSession

Guard = Callable[[ASGIConnection, BaseRouteHandler], Coroutine[None, None, None]]

DEV_SUPERUSER = AuthenticatedUser(sub="dev", name="Dev User")

# Role hierarchy, single source of truth. A held role satisfies a minimum when its rank is at least as high.
ROLE_RANK = {Role.VIEWER: 1, Role.SUBMITTER: 2, Role.EDITOR: 3, Role.LAB_ADMIN: 4, Role.SUPERUSER: 5}

# ASGI scope key for caching a request's resolved roles across its guards
_ROLES_SCOPE_KEY = "_eos_user_roles"


def role_satisfies(held: Role, minimum: Role) -> bool:
    """True if holding ``held`` meets a ``minimum`` role requirement."""
    return ROLE_RANK[held] >= ROLE_RANK[minimum]


class HasOwner(Protocol):
    owner: str


async def get_user_roles(db: AsyncDbSession, sub: str) -> list[UserRoleModel]:
    """Get a principal's effective roles. An API token resolves to its owner, so it always
    authorizes with the owner's live roles."""
    result = await db.execute(select(UserRoleModel).where(UserRoleModel.sub == sub))
    return list(result.scalars().all())


def is_auth_disabled(connection: ASGIConnection) -> bool:
    return "token_validator" not in connection.app.state


def stamp_owner(data: HasOwner, user: AuthenticatedUser) -> None:
    """Record the submitter as the owner. With auth on, the owner is always the authenticated user; with
    auth off, any client-supplied owner is kept but an empty owner is never persisted."""
    if user is not DEV_SUPERUSER or not data.owner:
        data.owner = user.sub


async def _user_roles(connection: ASGIConnection) -> list[UserRoleModel]:
    """Resolve and cache the caller's roles for the lifetime of the request (shared across its guards)."""
    cached = connection.scope.get(_ROLES_SCOPE_KEY)
    if cached is not None:
        return cached
    db_interface = connection.app.state["db_interface"]
    async with db_interface.get_async_session() as db:
        roles = await get_user_roles(db, connection.user.sub)
    connection.scope[_ROLES_SCOPE_KEY] = roles
    return roles


def require_role(minimum: Role) -> Guard:
    """Require at least the given role by rank. Any higher role (up to superuser) qualifies."""

    async def guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
        if is_auth_disabled(connection):
            return
        roles = await _user_roles(connection)
        if not any(role_satisfies(role.role, minimum) for role in roles):
            raise PermissionDeniedException(detail=f"Requires the {minimum.value.lower()} role")

    return guard


def require_superuser() -> Guard:
    """Require the local superuser role for this instance."""

    async def guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
        if is_auth_disabled(connection):
            return
        roles = await _user_roles(connection)
        if not any(role.role == Role.SUPERUSER for role in roles):
            raise PermissionDeniedException(detail="Requires the superuser role")

    return guard


def require_lab_admin(lab_path_param: str) -> Guard:
    """Require lab admin of the lab named by the given path parameter (or superuser)."""

    async def guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
        if is_auth_disabled(connection):
            return
        lab_name = connection.path_params.get(lab_path_param)
        roles = await _user_roles(connection)
        if not any(
            role.role == Role.SUPERUSER or (role.role == Role.LAB_ADMIN and role.lab_name == lab_name) for role in roles
        ):
            raise PermissionDeniedException(detail=f"Requires lab admin of lab '{lab_name}'")

    return guard
