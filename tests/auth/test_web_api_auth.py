from typing import ClassVar

import pytest
from litestar import get, Controller, Router
from litestar.di import Provide
from litestar.middleware import DefineMiddleware
from litestar.testing import create_test_client

from eos.auth.api_tokens import EOS_TOKEN_PREFIX, hash_api_token
from eos.auth.authorization import require_lab_admin, require_role, require_superuser
from eos.auth.entities.api_token import ApiTokenModel
from eos.auth.entities.user_role import AuthenticatedUser, Role, UserRoleModel
from eos.auth.middleware import EosAuthenticationMiddleware
from eos.auth.token_validator import TokenValidationError, TokenValidator
from eos.configuration.eos_config import AuthConfig, DatabaseType, DbConfig, SqliteDbConfig
from eos.database.sqlite_db_interface import SqliteDbInterface
from eos.web_api.dependencies import provide_current_user

TOKENS = {
    "superuser-token": AuthenticatedUser(sub="root"),
    "submitter-token": AuthenticatedUser(sub="submitter-user"),
    "editor-token": AuthenticatedUser(sub="editor-user"),
    "viewer-token": AuthenticatedUser(sub="viewer-user"),
    "labadmin-token": AuthenticatedUser(sub="labadmin-user"),
    "norole-token": AuthenticatedUser(sub="nobody"),
}

PAT_OF_SUBMITTER = EOS_TOKEN_PREFIX + "submitter-secret"
PAT_OF_NOBODY = EOS_TOKEN_PREFIX + "norole-secret"


class StubValidator:
    """Stands in for the OIDC paths. EOS-issued tokens take the real local resolution path."""

    def __init__(self, db_interface):
        self._validator = TokenValidator(AuthConfig(enabled=False, _env_file=None), db_interface)

    async def validate(self, token: str) -> AuthenticatedUser:
        if token.startswith(EOS_TOKEN_PREFIX):
            return await self._validator.validate(token)
        if token not in TOKENS:
            raise TokenValidationError("Invalid token")
        return TOKENS[token]

    async def fetch_userinfo(self, token: str) -> dict | None:
        return None


class ThingController(Controller):
    path = "/things"
    guards: ClassVar = [require_role(Role.VIEWER)]

    @get("/")
    async def read(self) -> dict:
        return {"ok": True}

    @get("/submit", guards=[require_role(Role.SUBMITTER)])
    async def submit(self) -> dict:
        return {"ok": True}

    @get("/edit", guards=[require_role(Role.EDITOR)])
    async def edit(self) -> dict:
        return {"ok": True}

    @get("/admin", guards=[require_superuser()])
    async def admin(self) -> dict:
        return {"ok": True}

    @get("/labs/{lab_name:str}", guards=[require_lab_admin("lab_name")])
    async def lab_op(self, lab_name: str) -> dict:
        return {"ok": True}

    @get("/me")
    async def me(self, user: AuthenticatedUser) -> dict:
        return {"sub": user.sub}


@get("/health")
async def health() -> dict:
    return {"ok": True}


@pytest.fixture
async def db_interface():
    db_interface = SqliteDbInterface(DbConfig(type=DatabaseType.SQLITE, sqlite=SqliteDbConfig(in_memory=True)))
    await db_interface.initialize_database()
    async with db_interface.get_async_session() as db:
        db.add(UserRoleModel(sub="root", role=Role.SUPERUSER, granted_by="test"))
        db.add(UserRoleModel(sub="submitter-user", role=Role.SUBMITTER, granted_by="test"))
        db.add(UserRoleModel(sub="editor-user", role=Role.EDITOR, granted_by="test"))
        db.add(UserRoleModel(sub="viewer-user", role=Role.VIEWER, granted_by="test"))
        db.add(UserRoleModel(sub="labadmin-user", role=Role.LAB_ADMIN, lab_name="lab_a", granted_by="test"))
        db.add(ApiTokenModel(owner_sub="submitter-user", token_hash=hash_api_token(PAT_OF_SUBMITTER)))
        db.add(ApiTokenModel(owner_sub="nobody", token_hash=hash_api_token(PAT_OF_NOBODY)))
    return db_interface


@pytest.fixture
def client(db_interface):
    router = Router(path="/api", route_handlers=[ThingController, health])
    with create_test_client(
        route_handlers=[router],
        middleware=[DefineMiddleware(EosAuthenticationMiddleware, exclude=["^/api/health"])],
        state={"db_interface": db_interface, "token_validator": StubValidator(db_interface)},
        dependencies={"user": Provide(provide_current_user, sync_to_thread=False)},
    ) as client:
        yield client


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_no_token_rejected(client):
    assert client.get("/api/things/").status_code == 401


def test_invalid_token_rejected(client):
    assert client.get("/api/things/", headers=auth("bogus")).status_code == 401


def test_health_open(client):
    assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize(
    "token", ["viewer-token", "submitter-token", "editor-token", "labadmin-token", "superuser-token"]
)
def test_read_allowed_for_all_roles(client, token):
    assert client.get("/api/things/", headers=auth(token)).status_code == 200


def test_read_rejected_without_role(client):
    assert client.get("/api/things/", headers=auth("norole-token")).status_code == 403


def test_submit_rejected_for_viewer(client):
    assert client.get("/api/things/submit", headers=auth("viewer-token")).status_code == 403


@pytest.mark.parametrize("token", ["submitter-token", "editor-token", "labadmin-token", "superuser-token"])
def test_submit_allowed_for_submitter_and_above(client, token):
    assert client.get("/api/things/submit", headers=auth(token)).status_code == 200


@pytest.mark.parametrize("token", ["viewer-token", "submitter-token"])
def test_edit_rejected_below_editor(client, token):
    assert client.get("/api/things/edit", headers=auth(token)).status_code == 403


@pytest.mark.parametrize("token", ["editor-token", "labadmin-token", "superuser-token"])
def test_edit_allowed_for_editor_and_above(client, token):
    assert client.get("/api/things/edit", headers=auth(token)).status_code == 200


@pytest.mark.parametrize("token", ["viewer-token", "submitter-token", "editor-token", "labadmin-token"])
def test_admin_rejected_for_non_superuser(client, token):
    assert client.get("/api/things/admin", headers=auth(token)).status_code == 403


def test_admin_allowed_for_superuser(client):
    assert client.get("/api/things/admin", headers=auth("superuser-token")).status_code == 200


def test_lab_admin_scoped_to_lab(client):
    assert client.get("/api/things/labs/lab_a", headers=auth("labadmin-token")).status_code == 200
    assert client.get("/api/things/labs/lab_b", headers=auth("labadmin-token")).status_code == 403


def test_lab_admin_endpoint_allows_superuser(client):
    assert client.get("/api/things/labs/lab_b", headers=auth("superuser-token")).status_code == 200


def test_lab_admin_endpoint_rejects_editor(client):
    # Editor outranks submitter but is below lab admin, so lab-scoped ops are denied
    assert client.get("/api/things/labs/lab_a", headers=auth("editor-token")).status_code == 403


def test_current_user_dependency(client):
    response = client.get("/api/things/me", headers=auth("submitter-token"))
    assert response.json() == {"sub": "submitter-user"}


def test_api_token_inherits_owner_roles(client):
    # The token resolves to its owner, so it acts with submitter-user's live SUBMITTER role
    assert client.get("/api/things/", headers=auth(PAT_OF_SUBMITTER)).status_code == 200
    assert client.get("/api/things/submit", headers=auth(PAT_OF_SUBMITTER)).status_code == 200
    assert client.get("/api/things/edit", headers=auth(PAT_OF_SUBMITTER)).status_code == 403
    assert client.get("/api/things/admin", headers=auth(PAT_OF_SUBMITTER)).status_code == 403


def test_api_token_for_roleless_owner_is_denied(client):
    # Owner has no roles, so the token has none either (no stale snapshot to abuse)
    assert client.get("/api/things/", headers=auth(PAT_OF_NOBODY)).status_code == 403


def test_unknown_api_token_rejected(client):
    assert client.get("/api/things/", headers=auth(EOS_TOKEN_PREFIX + "nonesuch")).status_code == 401


def test_auth_disabled_allows_all(db_interface):
    router = Router(path="/api", route_handlers=[ThingController, health])
    with create_test_client(
        route_handlers=[router],
        state={"db_interface": db_interface},
        dependencies={"user": Provide(provide_current_user, sync_to_thread=False)},
    ) as client:
        assert client.get("/api/things/").status_code == 200
        assert client.get("/api/things/admin").status_code == 200
        assert client.get("/api/things/me").json() == {"sub": "dev"}
