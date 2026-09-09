import json
import subprocess

import httpx
import pytest
import respx

from eos.auth.zitadel_bootstrap import ZitadelBootstrapClient, read_bootstrap_pat

ISSUER = "http://localhost:8080"

# Canned responses for a fresh Zitadel instance (everything created from scratch).
DEFAULT_ROUTES: dict[str, tuple[int, dict]] = {
    "/v2/organizations/_search": (200, {"result": []}),
    "/v2/organizations": (200, {"organizationId": "org-1"}),
    "/management/v1/projects/_search": (200, {"result": []}),
    "/management/v1/projects": (200, {"id": "proj-1"}),
    "/management/v1/projects/proj-1/roles": (200, {}),
    "/management/v1/projects/proj-1/apps/_search": (200, {"result": []}),
    "/management/v1/projects/proj-1/apps/oidc": (200, {"clientId": "web-client"}),
    "/management/v1/projects/proj-1/apps/api": (200, {"clientId": "api-client", "clientSecret": "api-secret"}),
    "/v2/users": (200, {"result": []}),
    "/management/v1/users/machine": (200, {"userId": "user-1"}),
    "/management/v1/orgs/me/members": (200, {}),
    "/management/v1/users/user-1/pats": (200, {"token": "pat-xyz"}),
}


@pytest.fixture
def router():
    with respx.mock(base_url=ISSUER, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def client():
    bootstrap = ZitadelBootstrapClient(ISSUER, "admin-pat")
    yield bootstrap
    bootstrap.close()


def _routes(router, overrides: dict[str, tuple[int, dict]] | None = None) -> dict:
    spec = {**DEFAULT_ROUTES, **(overrides or {})}
    return {p: router.post(p).mock(return_value=httpx.Response(s, json=j)) for p, (s, j) in spec.items()}


def _last_body(route) -> dict:
    return json.loads(route.calls.last.request.content)


def test_full_bootstrap_sequence(router, client):
    _routes(router)

    org_id = client.ensure_org("EOS")
    project_id = client.ensure_project("EOS")
    client.ensure_project_role(project_id, "superuser")
    web_client_id = client.ensure_oidc_app(project_id, f"{ISSUER}/cb", f"{ISSUER}/signin", dev_mode=True)
    api_client_id, api_client_secret = client.ensure_api_app(project_id)
    user_id = client.ensure_machine_user("eos-user-admin")
    client.ensure_org_member(user_id, ["ORG_USER_MANAGER"])
    pat = client.create_pat(user_id)

    assert (org_id, project_id) == ("org-1", "proj-1")
    assert (web_client_id, api_client_id, api_client_secret) == ("web-client", "api-client", "api-secret")
    assert (user_id, pat) == ("user-1", "pat-xyz")


def test_org_id_targeted_in_subsequent_requests(router, client):
    routes = _routes(router)
    client.ensure_org("EOS")
    client.ensure_project("EOS")
    assert routes["/management/v1/projects"].calls.last.request.headers["x-zitadel-orgid"] == "org-1"


def test_project_created_with_role_assertion(router, client):
    routes = _routes(router)
    client.ensure_org("EOS")
    client.ensure_project("EOS")
    assert _last_body(routes["/management/v1/projects"])["projectRoleAssertion"] is True


def test_oidc_app_requests_jwt_with_role_assertion(router, client):
    routes = _routes(router)
    client.ensure_oidc_app("proj-1", f"{ISSUER}/cb", f"{ISSUER}/signin", dev_mode=True)
    body = _last_body(routes["/management/v1/projects/proj-1/apps/oidc"])
    assert body["accessTokenType"] == "OIDC_TOKEN_TYPE_JWT"
    assert body["accessTokenRoleAssertion"] is True
    assert body["authMethodType"] == "OIDC_AUTH_METHOD_TYPE_NONE"
    assert body["devMode"] is True


def test_api_app_uses_basic_auth(router, client):
    routes = _routes(router)
    client.ensure_api_app("proj-1")
    assert (
        _last_body(routes["/management/v1/projects/proj-1/apps/api"])["authMethodType"] == "API_AUTH_METHOD_TYPE_BASIC"
    )


def test_existing_role_conflict_is_tolerated(router, client):
    _routes(router, {"/management/v1/projects/proj-1/roles": (409, {})})
    client.ensure_project_role("proj-1", "superuser")  # must not raise


def test_existing_org_is_reused_without_create(router, client):
    routes = _routes(router, {"/v2/organizations/_search": (200, {"result": [{"id": "org-existing", "name": "EOS"}]})})
    assert client.ensure_org("EOS") == "org-existing"
    assert not routes["/v2/organizations"].called


def test_existing_oidc_app_is_reused(router, client):
    existing = {"result": [{"name": "EOS Web UI", "oidcConfig": {"clientId": "existing-web"}}]}
    routes = _routes(router, {"/management/v1/projects/proj-1/apps/_search": (200, existing)})
    assert client.ensure_oidc_app("proj-1", f"{ISSUER}/cb", f"{ISSUER}/signin", dev_mode=False) == "existing-web"
    assert not routes["/management/v1/projects/proj-1/apps/oidc"].called


def test_existing_api_app_returns_no_secret(router, client):
    existing = {"result": [{"name": "EOS API", "apiConfig": {"clientId": "existing-api"}}]}
    _routes(router, {"/management/v1/projects/proj-1/apps/_search": (200, existing)})
    client_id, secret = client.ensure_api_app("proj-1")
    assert client_id == "existing-api"
    assert secret is None


def test_unexpected_error_is_raised(router, client):
    _routes(router, {"/management/v1/projects/proj-1/roles": (500, {})})
    with pytest.raises(httpx.HTTPStatusError):
        client.ensure_project_role("proj-1", "superuser")


def test_disable_registration_turns_off_when_enabled(router, client):
    policy = {"allowRegister": True, "allowUsernamePassword": True, "passwordCheckLifetime": "864000s"}
    router.get("/admin/v1/policies/login").mock(return_value=httpx.Response(200, json={"policy": policy}))
    put = router.put("/admin/v1/policies/login").mock(return_value=httpx.Response(200, json={}))

    client.disable_registration()

    assert put.called
    body = json.loads(put.calls.last.request.content)
    assert body["allowRegister"] is False
    assert body["allowUsernamePassword"] is True  # other fields preserved


def test_disable_registration_noop_when_already_off(router, client):
    router.get("/admin/v1/policies/login").mock(return_value=httpx.Response(200, json={"policy": {}}))
    put = router.put("/admin/v1/policies/login").mock(return_value=httpx.Response(200, json={}))

    client.disable_registration()

    assert not put.called


def test_wait_ready_polls_discovery(router, client):
    router.get("/.well-known/openid-configuration").mock(return_value=httpx.Response(200, json={"issuer": ISSUER}))
    client.wait_ready(timeout_s=5)  # must return without raising


def test_read_bootstrap_pat(monkeypatch):
    class FakeCompleted:
        returncode = 0
        stdout = "the-pat\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompleted())
    assert read_bootstrap_pat() == "the-pat"
