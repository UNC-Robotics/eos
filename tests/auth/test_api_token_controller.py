from collections.abc import AsyncGenerator

import pytest
from litestar import Router
from litestar.di import Provide
from litestar.middleware import DefineMiddleware
from litestar.testing import create_test_client

from eos.auth.api_tokens import EOS_TOKEN_PREFIX
from eos.auth.entities.user_role import AuthenticatedUser, Role, UserRoleModel
from eos.auth.middleware import EosAuthenticationMiddleware
from eos.auth.token_validator import TokenValidationError, TokenValidator
from eos.configuration.eos_config import AuthConfig, DatabaseType, DbConfig, SqliteDbConfig
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.database.sqlite_db_interface import SqliteDbInterface
from eos.web_api.controllers.api_token_controller import ApiTokenController
from eos.web_api.dependencies import provide_current_user

SESSION_TOKENS = {
    "alice-token": AuthenticatedUser(sub="alice"),
    "bob-token": AuthenticatedUser(sub="bob"),
}


class Validator:
    """Resolves EOS tokens for real and stands in for the OIDC paths."""

    def __init__(self, db_interface):
        self._validator = TokenValidator(AuthConfig(enabled=False, _env_file=None), db_interface)

    async def validate(self, token: str) -> AuthenticatedUser:
        if token.startswith(EOS_TOKEN_PREFIX):
            return await self._validator.validate(token)
        if token not in SESSION_TOKENS:
            raise TokenValidationError("Invalid token")
        return SESSION_TOKENS[token]

    async def fetch_userinfo(self, token: str) -> dict | None:
        return None


@pytest.fixture
async def db_interface():
    db_interface = SqliteDbInterface(DbConfig(type=DatabaseType.SQLITE, sqlite=SqliteDbConfig(in_memory=True)))
    await db_interface.initialize_database()
    async with db_interface.get_async_session() as db:
        db.add(UserRoleModel(sub="alice", role=Role.EDITOR, granted_by="test"))
        db.add(UserRoleModel(sub="bob", role=Role.VIEWER, granted_by="test"))
    return db_interface


@pytest.fixture
def client(db_interface):
    async def provide_db() -> AsyncGenerator[AsyncDbSession, None]:
        async with db_interface.get_async_session() as db:
            yield db

    with create_test_client(
        route_handlers=[Router(path="/api", route_handlers=[ApiTokenController])],
        middleware=[DefineMiddleware(EosAuthenticationMiddleware)],
        state={"db_interface": db_interface, "token_validator": Validator(db_interface)},
        dependencies={
            "db": Provide(provide_db),
            "user": Provide(provide_current_user, sync_to_thread=False),
        },
    ) as client:
        yield client


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_token(client, owner: str = "alice-token", label: str | None = "laptop") -> dict:
    response = client.post("/api/api-tokens/", json={"label": label}, headers=auth(owner))
    assert response.status_code == 201, response.text
    return response.json()


def test_created_token_is_returned_once_and_usable(client):
    created = create_token(client)
    assert created["token"].startswith(EOS_TOKEN_PREFIX)
    assert created["owner_sub"] == "alice"

    # The new token authenticates as its owner and carries the owner's roles
    listed = client.get("/api/api-tokens/", headers=auth(created["token"]))
    assert listed.status_code == 200
    assert [t["label"] for t in listed.json()] == ["laptop"]


def test_listing_never_exposes_the_secret(client):
    create_token(client)
    response = client.get("/api/api-tokens/", headers=auth("alice-token"))
    assert EOS_TOKEN_PREFIX not in response.text
    assert all("token" not in row for row in response.json())


def test_tokens_are_scoped_to_their_owner(client):
    create_token(client)
    assert client.get("/api/api-tokens/", headers=auth("bob-token")).json() == []


def test_revoked_token_stops_working(client):
    created = create_token(client)
    assert client.delete(f"/api/api-tokens/{created['id']}", headers=auth("alice-token")).status_code == 204
    assert client.get("/api/api-tokens/", headers=auth(created["token"])).status_code == 401
    assert client.get("/api/api-tokens/", headers=auth("alice-token")).json() == []


def test_cannot_revoke_another_users_token(client):
    created = create_token(client)
    assert client.delete(f"/api/api-tokens/{created['id']}", headers=auth("bob-token")).status_code == 404
    # Still works for its owner
    assert client.get("/api/api-tokens/", headers=auth(created["token"])).status_code == 200


def test_revoking_an_unknown_token_is_not_found(client):
    assert client.delete("/api/api-tokens/999", headers=auth("alice-token")).status_code == 404
