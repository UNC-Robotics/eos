import contextlib
import logging
from dataclasses import replace

from eos.auth.api_tokens import EOS_TOKEN_PREFIX
from eos.auth.entities.user_identity import UserIdentityModel
from eos.auth.entities.user_role import AuthenticatedUser
from eos.auth.token_validator import TokenValidator
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface

log = logging.getLogger(__name__)

# Subs recorded since this process started. A restart refreshes what EOS knows about a user.
_synced: set[str] = set()


def reset_sync_cache() -> None:
    """Forget which subs have been recorded. Used by tests."""
    _synced.clear()


async def record_identity(
    db_interface: AbstractSqlDbInterface, validator: TokenValidator, user: AuthenticatedUser, token: str
) -> None:
    """Record what a token tells us about its user, so EOS can show and look up people without
    querying the identity provider. Runs once per user per process and never blocks a request."""
    if user.sub in _synced:
        return
    if not user.email and not token.startswith(EOS_TOKEN_PREFIX):
        # A provider that withholds these claims should not cost a lookup on every request
        with contextlib.suppress(Exception):
            claims = await validator.fetch_userinfo(token)
            if claims:
                user = _enrich(user, claims)
    try:
        await _write(db_interface, user)
        _synced.add(user.sub)
    except Exception:
        log.debug("Could not record the identity of %s", user.sub, exc_info=True)


def _enrich(user: AuthenticatedUser, claims: dict) -> AuthenticatedUser:
    return replace(
        user,
        email=user.email or claims.get("email"),
        name=user.name or claims.get("name") or claims.get("preferred_username"),
    )


async def _write(db_interface: AbstractSqlDbInterface, user: AuthenticatedUser) -> None:
    async with db_interface.get_async_session() as db:
        existing = await db.get(UserIdentityModel, user.sub)
        if existing is None:
            db.add(UserIdentityModel(sub=user.sub, email=_normalize_email(user.email), name=user.name))
        else:
            existing.email = _normalize_email(user.email) or existing.email
            existing.name = user.name or existing.name


def _normalize_email(email: str | None) -> str | None:
    return email.strip().lower() if email else None
