import secrets
import string

import httpx

from eos.configuration.eos_config import AuthConfig

ZITADEL_COMPLEXITY_SUFFIX = "!1Aa"  # satisfies Zitadel's default complexity policy (upper, lower, digit, symbol)


def generate_complexity_password(length: int = 14) -> str:
    """Generate a random password satisfying Zitadel's default complexity policy."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length)) + ZITADEL_COMPLEXITY_SUFFIX


class ZitadelClient:
    """Client for the Zitadel management APIs, authenticated with a service user PAT.

    Synchronous; only for CLI use. Never use in the orchestrator or REST API.
    """

    def __init__(self, config: AuthConfig):
        if not (config.issuer and config.service_user_pat and config.org_id):
            raise ValueError("auth.issuer, auth.org_id, and auth.service_user_pat are required for account management")
        self._config = config
        self._http = httpx.Client(
            base_url=config.issuer.rstrip("/"),
            headers={
                "Authorization": f"Bearer {config.service_user_pat}",
                "x-zitadel-orgid": config.org_id,
            },
            timeout=15,
            verify=config.ca_bundle or True,
        )

    def create_user(self, username: str, email: str, given_name: str, family_name: str, temporary_password: str) -> str:
        """Create a human user with a temporary password that must be changed at first login. Returns the user ID."""
        response = self._http.post(
            "/v2/users/human",
            json={
                "username": username,
                "organization": {"orgId": self._config.org_id},
                "profile": {"givenName": given_name, "familyName": family_name},
                "email": {"email": email, "isVerified": True},
                "password": {"password": temporary_password, "changeRequired": True},
            },
        )
        response.raise_for_status()
        return response.json()["userId"]

    def list_users(self) -> list[dict]:
        """List all human users in the organization."""
        response = self._http.post(
            "/v2/users",
            json={
                "query": {"limit": 1000},
                "queries": [
                    {"organizationIdQuery": {"organizationId": self._config.org_id}},
                    {"typeQuery": {"type": "TYPE_HUMAN"}},
                ],
            },
        )
        response.raise_for_status()
        return response.json().get("result", [])

    def deactivate_user(self, user_id: str) -> None:
        self._http.post(f"/v2/users/{user_id}/deactivate").raise_for_status()

    def reactivate_user(self, user_id: str) -> None:
        self._http.post(f"/v2/users/{user_id}/reactivate").raise_for_status()

    def __enter__(self) -> "ZitadelClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()
