from typing import ClassVar

from litestar import Controller, delete, get, post
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, select

from eos.auth.api_tokens import generate_api_token
from eos.auth.authorization import require_role
from eos.auth.entities.api_token import ApiToken, ApiTokenModel, CreatedApiToken
from eos.auth.entities.user_role import AuthenticatedUser, Role
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.web_api.exception_handling import APIError


class CreateApiTokenRequest(BaseModel):
    label: str | None = None


class ApiTokenController(Controller):
    """Self-service API tokens. Each token acts with its owner's live roles."""

    path = "/api-tokens"
    guards: ClassVar = [require_role(Role.VIEWER)]

    @get("/")
    async def list_tokens(self, db: AsyncDbSession, user: AuthenticatedUser) -> list[ApiToken]:
        """List the caller's API tokens."""
        result = await db.execute(
            select(ApiTokenModel).where(ApiTokenModel.owner_sub == user.sub).order_by(ApiTokenModel.created_at)
        )
        return [ApiToken.model_validate(token) for token in result.scalars().all()]

    @post("/")
    async def create_token(
        self, data: CreateApiTokenRequest, db: AsyncDbSession, user: AuthenticatedUser
    ) -> CreatedApiToken:
        """Issue a token for the caller. The secret is returned here and never stored."""
        secret, token_hash = generate_api_token()
        token = ApiTokenModel(owner_sub=user.sub, token_hash=token_hash, label=data.label)
        db.add(token)
        await db.commit()
        return CreatedApiToken(**ApiToken.model_validate(token).model_dump(), token=secret)

    @delete("/{token_id:int}")
    async def revoke_token(self, token_id: int, db: AsyncDbSession, user: AuthenticatedUser) -> None:
        """Revoke one of the caller's tokens."""
        result = await db.execute(
            sa_delete(ApiTokenModel).where(ApiTokenModel.id == token_id, ApiTokenModel.owner_sub == user.sub)
        )
        if result.rowcount == 0:
            raise APIError(status_code=404, detail="Token not found")
        await db.commit()
