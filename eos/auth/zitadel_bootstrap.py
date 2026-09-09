import subprocess
import time
from urllib.parse import urlparse

import httpx

# Targets Zitadel v4: org via the resource API, everything else via the stable management v1 API.
CONFLICT_STATUS = 409
PAT_EXPIRATION = "2099-01-01T00:00:00Z"
READY_POLL_INTERVAL = 2.0
ORG_USER_MANAGER_ROLE = "ORG_USER_MANAGER"
LOCAL_HOSTS = ("localhost", "127.0.0.1")


def _localhost_variants(url: str) -> list[str]:
    """Return both ``localhost`` and ``127.0.0.1`` spellings of a local URL (else just the URL), so an
    OAuth redirect works whichever host the browser uses (``next start`` advertises 127.0.0.1)."""
    parsed = urlparse(url)
    if parsed.hostname not in LOCAL_HOSTS:
        return [url]
    return [parsed._replace(netloc=parsed.netloc.replace(parsed.hostname, host, 1)).geturl() for host in LOCAL_HOSTS]


def read_bootstrap_pat(compose_project_name: str = "eos", timeout_s: int = 120) -> str:
    """Read the Zitadel bootstrap admin PAT from the shared docker volume, polling until it is written."""
    volume = f"{compose_project_name}_zitadel_bootstrap"
    cmd = ["docker", "run", "--rm", "-v", f"{volume}:/b:ro", "alpine", "cat", "/b/admin-sa.pat"]
    deadline = time.monotonic() + timeout_s
    last_error = "bootstrap PAT not yet written"
    while time.monotonic() < deadline:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        token = result.stdout.strip()
        if result.returncode == 0 and token:
            return token
        last_error = result.stderr.strip() or last_error
        time.sleep(READY_POLL_INTERVAL)
    raise RuntimeError(f"Timed out reading the Zitadel bootstrap PAT from volume '{volume}': {last_error}")


class ZitadelBootstrapClient:
    """One-time programmatic Zitadel setup, authenticated with the instance-admin bootstrap PAT.

    Synchronous; CLI-only. Mirrors ZitadelClient. Every method is idempotent so setup can be re-run.
    """

    def __init__(self, issuer: str, admin_pat: str, ca_bundle: str | None = None) -> None:
        self._issuer = issuer.rstrip("/")
        self._org_id: str | None = None
        self._http = httpx.Client(
            base_url=self._issuer,
            headers={"Authorization": f"Bearer {admin_pat}"},
            timeout=30,
            verify=ca_bundle or True,
        )

    def close(self) -> None:
        self._http.close()

    def wait_ready(self, timeout_s: int = 120) -> None:
        """Poll the OIDC discovery document until Zitadel serves it through the proxy."""
        url = f"{self._issuer}/.well-known/openid-configuration"
        deadline = time.monotonic() + timeout_s
        last_error = "no response"
        while time.monotonic() < deadline:
            try:
                response = self._http.get("/.well-known/openid-configuration", timeout=5)
                if response.status_code == httpx.codes.OK and "issuer" in response.json():
                    return
                last_error = f"status {response.status_code}"
            except (httpx.HTTPError, ValueError) as e:
                last_error = str(e)
            time.sleep(READY_POLL_INTERVAL)
        raise RuntimeError(f"Timed out waiting for Zitadel at {url}: {last_error}")

    # Login policy fields preserved verbatim when updating; second/multi factors are managed separately.
    _LOGIN_POLICY_FIELDS = (
        "allowUsernamePassword",
        "allowExternalIdp",
        "forceMfa",
        "forceMfaLocalOnly",
        "passwordlessType",
        "hidePasswordReset",
        "ignoreUnknownUsernames",
        "allowDomainDiscovery",
        "disableLoginWithEmail",
        "disableLoginWithPhone",
        "defaultRedirectUri",
        "passwordCheckLifetime",
        "externalLoginCheckLifetime",
        "mfaInitSkipLifetime",
        "secondFactorCheckLifetime",
        "multiFactorCheckLifetime",
    )

    def disable_registration(self) -> None:
        """Turn off self-registration in the instance login policy so the sign-up link disappears."""
        response = self._http.get("/admin/v1/policies/login")
        response.raise_for_status()
        policy = response.json()["policy"]
        if not policy.get("allowRegister"):
            return
        body = {field: policy[field] for field in self._LOGIN_POLICY_FIELDS if field in policy}
        body["allowRegister"] = False
        self._http.put("/admin/v1/policies/login", json=body).raise_for_status()

    def relax_password_complexity(self) -> None:
        """Drop the instance password complexity requirements to just a non-empty password."""
        self._http.put(
            "/admin/v1/policies/password/complexity",
            json={
                "minLength": "1",
                "hasUppercase": False,
                "hasLowercase": False,
                "hasNumber": False,
                "hasSymbol": False,
            },
        ).raise_for_status()

    def ensure_org(self, name: str = "EOS") -> str:
        """Find or create the organization, then target it for all subsequent calls. Returns its ID."""
        org_id = self._find_org(name)
        if org_id is None:
            response = self._http.post("/v2/organizations", json={"name": name})
            response.raise_for_status()
            org_id = response.json()["organizationId"]
        self._org_id = org_id
        self._http.headers["x-zitadel-orgid"] = org_id
        return org_id

    def ensure_project(self, name: str = "EOS") -> str:
        """Find or create the project with role assertion enabled. Returns its ID."""
        existing = self._find_project(name)
        if existing:
            return existing
        response = self._http.post("/management/v1/projects", json={"name": name, "projectRoleAssertion": True})
        response.raise_for_status()
        return response.json()["id"]

    def ensure_project_role(self, project_id: str, role_key: str = "superuser") -> None:
        """Add the project role; an existing role is treated as success."""
        try:
            self._http.post(
                f"/management/v1/projects/{project_id}/roles",
                json={"roleKey": role_key, "displayName": role_key.capitalize()},
            ).raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code != CONFLICT_STATUS:
                raise

    def ensure_oidc_app(self, project_id: str, redirect_uri: str, post_logout_uri: str, dev_mode: bool) -> str:
        """Find or create the OIDC web app (code + PKCE, JWT tokens, role assertion). Returns the client ID."""
        existing = self._find_app_client_id(project_id, "EOS Web UI")
        if existing:
            return existing
        response = self._http.post(
            f"/management/v1/projects/{project_id}/apps/oidc",
            json={
                "name": "EOS Web UI",
                "redirectUris": _localhost_variants(redirect_uri),
                "postLogoutRedirectUris": _localhost_variants(post_logout_uri),
                "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
                "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE", "OIDC_GRANT_TYPE_REFRESH_TOKEN"],
                "appType": "OIDC_APP_TYPE_WEB",
                "authMethodType": "OIDC_AUTH_METHOD_TYPE_NONE",
                "accessTokenType": "OIDC_TOKEN_TYPE_JWT",
                "accessTokenRoleAssertion": True,
                "idTokenRoleAssertion": True,
                # Put email/name/profile claims in the ID token (Auth.js reads the profile from it)
                "idTokenUserinfoAssertion": True,
                "devMode": dev_mode,
            },
        )
        response.raise_for_status()
        return response.json()["clientId"]

    def ensure_api_app(self, project_id: str) -> tuple[str, str | None]:
        """Find or create the API app (Basic auth, for token introspection).

        Returns (client_id, client_secret). The secret is None when the app already existed,
        since Zitadel only reveals it at creation.
        """
        existing = self._find_app_client_id(project_id, "EOS API")
        if existing:
            return existing, None
        response = self._http.post(
            f"/management/v1/projects/{project_id}/apps/api",
            json={"name": "EOS API", "authMethodType": "API_AUTH_METHOD_TYPE_BASIC"},
        )
        response.raise_for_status()
        data = response.json()
        return data["clientId"], data["clientSecret"]

    def ensure_machine_user(self, username: str = "eos-user-admin") -> str:
        """Find or create the account-management service user. Returns its ID."""
        existing = self._find_machine_user(username)
        if existing:
            return existing
        response = self._http.post(
            "/management/v1/users/machine",
            json={
                "userName": username,
                "name": "EOS User Admin",
                "description": "EOS account-management service user",
                "accessTokenType": "ACCESS_TOKEN_TYPE_BEARER",
            },
        )
        response.raise_for_status()
        return response.json()["userId"]

    def ensure_org_member(self, user_id: str, roles: list[str]) -> None:
        """Grant org member roles to the user; an existing membership is treated as success."""
        try:
            self._http.post(
                "/management/v1/orgs/me/members", json={"userId": user_id, "roles": roles}
            ).raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code != CONFLICT_STATUS:
                raise

    def create_pat(self, user_id: str) -> str:
        """Create a long-lived personal access token for the service user. Returns the token value."""
        response = self._http.post(f"/management/v1/users/{user_id}/pats", json={"expirationDate": PAT_EXPIRATION})
        response.raise_for_status()
        return response.json()["token"]

    def _find_org(self, name: str) -> str | None:
        response = self._http.post("/v2/organizations/_search", json={})
        response.raise_for_status()
        for org in response.json().get("result", []):
            if org.get("name") == name:
                return org.get("id")
        return None

    def _find_project(self, name: str) -> str | None:
        response = self._http.post("/management/v1/projects/_search", json={})
        response.raise_for_status()
        for project in response.json().get("result", []):
            if project.get("name") == name:
                return project.get("id")
        return None

    def _find_app_client_id(self, project_id: str, name: str) -> str | None:
        response = self._http.post(f"/management/v1/projects/{project_id}/apps/_search", json={})
        response.raise_for_status()
        for app in response.json().get("result", []):
            if app.get("name") == name:
                config = app.get("oidcConfig") or app.get("apiConfig") or {}
                return config.get("clientId")
        return None

    def _find_machine_user(self, username: str) -> str | None:
        response = self._http.post(
            "/v2/users",
            json={
                "queries": [
                    {"organizationIdQuery": {"organizationId": self._org_id}},
                    {"typeQuery": {"type": "TYPE_MACHINE"}},
                ]
            },
        )
        response.raise_for_status()
        for user in response.json().get("result", []):
            if user.get("username") == username:
                return user.get("userId")
        return None
