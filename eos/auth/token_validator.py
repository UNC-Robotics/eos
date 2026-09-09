import hashlib
import time

import httpx
import jwt
from jwt import InvalidTokenError, PyJWK

from eos.auth.api_tokens import EOS_TOKEN_PREFIX, resolve_api_token
from eos.auth.entities.user_role import AuthenticatedUser
from eos.configuration.eos_config import AuthConfig
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface

JWT_SEGMENTS = 3
MAX_INTROSPECTION_CACHE = 1024


class TokenValidationError(Exception):
    """Raised when a bearer token cannot be validated."""


class TokenValidator:
    """Validates bearer tokens. EOS API tokens resolve locally, JWTs via JWKS, and other
    opaque tokens via introspection."""

    def __init__(self, config: AuthConfig, db_interface: AbstractSqlDbInterface | None = None):
        self._config = config
        self._db_interface = db_interface
        self._http: httpx.AsyncClient | None = None

        self._oidc_metadata: dict | None = None
        self._jwks: dict[str, PyJWK] = {}
        self._jwks_fetched_at: float = 0.0
        # token hash -> (monotonic expiry, user)
        self._introspection_cache: dict[str, tuple[float, AuthenticatedUser]] = {}

    async def validate(self, token: str) -> AuthenticatedUser:
        """Validate a bearer token and return the authenticated user. Raises TokenValidationError."""
        if token.startswith(EOS_TOKEN_PREFIX):
            return await self._validate_eos_token(token)
        if len(token.split(".")) == JWT_SEGMENTS:
            return await self._validate_jwt(token)
        return await self._introspect(token)

    async def _validate_eos_token(self, token: str) -> AuthenticatedUser:
        """Resolve an EOS-issued API token against the local database."""
        if self._db_interface is None:
            raise TokenValidationError("EOS API tokens are unavailable without a database")
        async with self._db_interface.get_async_session() as db:
            user = await resolve_api_token(db, token)
        if user is None:
            raise TokenValidationError("Unknown API token")
        return user

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10, verify=self._config.ca_bundle or True)
        return self._http

    async def _get_oidc_metadata(self) -> dict:
        if self._oidc_metadata is None:
            url = f"{self._config.issuer.rstrip('/')}/.well-known/openid-configuration"
            response = await self._client().get(url)
            response.raise_for_status()
            self._oidc_metadata = response.json()
        return self._oidc_metadata

    async def fetch_userinfo(self, token: str) -> dict | None:
        """Fetch profile claims for a token. Zitadel asserts email into the ID token rather than
        the access token, so the access token alone usually identifies only the subject."""
        metadata = await self._get_oidc_metadata()
        endpoint = metadata.get("userinfo_endpoint")
        if not endpoint:
            return None
        response = await self._client().get(endpoint, headers={"Authorization": f"Bearer {token}"})
        if response.status_code != httpx.codes.OK:
            return None
        return response.json()

    async def _get_signing_key(self, kid: str) -> PyJWK:
        expired = time.monotonic() - self._jwks_fetched_at > self._config.jwks_cache_ttl
        if kid not in self._jwks or expired:
            metadata = await self._get_oidc_metadata()
            response = await self._client().get(metadata["jwks_uri"])
            response.raise_for_status()
            self._jwks = {key["kid"]: PyJWK.from_dict(key) for key in response.json()["keys"] if "kid" in key}
            self._jwks_fetched_at = time.monotonic()

        if kid not in self._jwks:
            raise TokenValidationError(f"Unknown signing key '{kid}'")
        return self._jwks[kid]

    async def _validate_jwt(self, token: str) -> AuthenticatedUser:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            if not kid:
                raise TokenValidationError("Token header missing 'kid'")
            key = await self._get_signing_key(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                audience=self._config.audiences,
                issuer=self._config.issuer,
                leeway=self._config.leeway_seconds,
            )
        except InvalidTokenError as e:
            raise TokenValidationError(f"Invalid token: {e}") from e

        return AuthenticatedUser(
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name") or claims.get("preferred_username"),
        )

    async def _introspect(self, token: str) -> AuthenticatedUser:
        if not (self._config.introspection_client_id and self._config.introspection_client_secret):
            raise TokenValidationError(
                "Received an opaque token but token introspection is not configured "
                "(set auth.introspection_client_id and auth.introspection_client_secret)"
            )

        cache_key = hashlib.sha256(token.encode()).hexdigest()
        cached = self._introspection_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        metadata = await self._get_oidc_metadata()
        response = await self._client().post(
            metadata["introspection_endpoint"],
            data={"token": token},
            auth=(self._config.introspection_client_id, self._config.introspection_client_secret),
        )
        if response.status_code != httpx.codes.OK:
            raise TokenValidationError(f"Token introspection failed with status {response.status_code}")

        claims = response.json()
        if not claims.get("active"):
            raise TokenValidationError("Token is not active")
        if not self._audience_accepted(claims):
            raise TokenValidationError("Token audience is not accepted")

        user = AuthenticatedUser(
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name") or claims.get("username"),
        )
        self._cache_introspection(cache_key, user, claims.get("exp"))
        return user

    def _audience_accepted(self, claims: dict) -> bool:
        """Reject introspected tokens issued for another client/app (mirrors the JWT audience check)."""
        aud = claims.get("aud", [])
        candidates = [aud] if isinstance(aud, str) else list(aud)
        if claims.get("client_id"):
            candidates.append(claims["client_id"])
        return any(candidate in self._config.audiences for candidate in candidates)

    def _cache_introspection(self, cache_key: str, user: AuthenticatedUser, exp: float | None) -> None:
        """Cache an introspection result, capping its lifetime by the token's own expiry and bounding size."""
        ttl = self._config.introspection_cache_ttl
        if isinstance(exp, (int, float)):
            ttl = min(ttl, max(0.0, exp - time.time()))
        now = time.monotonic()
        # Drop expired entries, then evict oldest (insertion order) until within bounds
        for expired in [key for key, (expiry, _) in self._introspection_cache.items() if expiry <= now]:
            del self._introspection_cache[expired]
        while len(self._introspection_cache) >= MAX_INTROSPECTION_CACHE:
            del self._introspection_cache[next(iter(self._introspection_cache))]
        self._introspection_cache[cache_key] = (now + ttl, user)
