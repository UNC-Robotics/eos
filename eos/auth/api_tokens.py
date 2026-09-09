import hashlib
import secrets

from sqlalchemy import select

from eos.auth.entities.api_token import ApiTokenModel
from eos.auth.entities.user_identity import UserIdentityModel
from eos.auth.entities.user_role import AuthenticatedUser
from eos.database.abstract_sql_db_interface import AsyncDbSession

EOS_TOKEN_PREFIX = "eos_pat_"  # noqa: S105
TOKEN_SECRET_BYTES = 32


def generate_api_token() -> tuple[str, str]:
    """Create a new API token. Returns the secret to reveal once and the hash to store."""
    token = EOS_TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_SECRET_BYTES)
    return token, hash_api_token(token)


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def resolve_api_token(db: AsyncDbSession, token: str) -> AuthenticatedUser | None:
    """Resolve an EOS API token to its owner. Returns None if the token is unknown."""
    result = await db.execute(
        select(ApiTokenModel.owner_sub, UserIdentityModel.email, UserIdentityModel.name)
        .outerjoin(UserIdentityModel, UserIdentityModel.sub == ApiTokenModel.owner_sub)
        .where(ApiTokenModel.token_hash == hash_api_token(token))
    )
    row = result.first()
    if row is None:
        return None
    return AuthenticatedUser(sub=row.owner_sub, email=row.email, name=row.name)
