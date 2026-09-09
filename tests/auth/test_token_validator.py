import base64
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK

from eos.auth.token_validator import TokenValidationError, TokenValidator
from eos.configuration.eos_config import AuthConfig

ISSUER = "https://zitadel.example.org"
AUDIENCE = "project-123"
KID = "key-1"


def _int_to_b64(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def jwks(private_key):
    public_numbers = private_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": KID,
                "use": "sig",
                "alg": "RS256",
                "n": _int_to_b64(public_numbers.n),
                "e": _int_to_b64(public_numbers.e),
            }
        ]
    }


def make_token(private_key, **overrides) -> str:
    claims = {
        "iss": ISSUER,
        "aud": [AUDIENCE],
        "sub": "user-1",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
        **overrides,
    }
    headers = {"kid": overrides.pop("kid", KID)} if "kid" in overrides else {"kid": KID}
    claims.pop("kid", None)
    return jwt.encode(claims, private_key, algorithm="RS256", headers=headers)


@pytest.fixture
def validator(jwks, monkeypatch):
    config = AuthConfig(enabled=True, issuer=ISSUER, project_id=AUDIENCE, _env_file=None)
    validator = TokenValidator(config)

    async def fake_metadata():
        return {"jwks_uri": f"{ISSUER}/oauth/v2/keys", "introspection_endpoint": f"{ISSUER}/oauth/v2/introspect"}

    jwks_fetches = {"count": 0}

    async def fake_get_signing_key(kid):
        jwks_fetches["count"] += 1
        keys = {key["kid"]: PyJWK.from_dict(key) for key in jwks["keys"]}
        if kid not in keys:
            raise TokenValidationError(f"Unknown signing key '{kid}'")
        return keys[kid]

    monkeypatch.setattr(validator, "_get_oidc_metadata", fake_metadata)
    monkeypatch.setattr(validator, "_get_signing_key", fake_get_signing_key)
    return validator


async def test_valid_token(validator, private_key):
    user = await validator.validate(make_token(private_key, email="a@b.org", name="Alice"))
    assert user.sub == "user-1"
    assert user.email == "a@b.org"
    assert user.name == "Alice"


async def test_expired_token_rejected(validator, private_key):
    token = make_token(private_key, exp=int(time.time()) - 120)
    with pytest.raises(TokenValidationError):
        await validator.validate(token)


async def test_expired_within_leeway_accepted(validator, private_key):
    token = make_token(private_key, exp=int(time.time()) - 10)
    user = await validator.validate(token)
    assert user.sub == "user-1"


async def test_wrong_issuer_rejected(validator, private_key):
    token = make_token(private_key, iss="https://evil.example.org")
    with pytest.raises(TokenValidationError):
        await validator.validate(token)


async def test_wrong_audience_rejected(validator, private_key):
    token = make_token(private_key, aud=["other-project"])
    with pytest.raises(TokenValidationError):
        await validator.validate(token)


async def test_wrong_signing_key_rejected(validator):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = make_token(other_key)
    with pytest.raises(TokenValidationError):
        await validator.validate(token)


async def test_opaque_token_without_introspection_config_rejected(validator):
    with pytest.raises(TokenValidationError, match="introspection"):
        await validator.validate("opaque-pat-token")


async def test_opaque_token_introspection(monkeypatch):
    config = AuthConfig(
        enabled=True,
        issuer=ISSUER,
        project_id=AUDIENCE,
        introspection_client_id="api-app",
        introspection_client_secret="secret",
        _env_file=None,
    )
    validator = TokenValidator(config)
    calls = {"count": 0}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"active": True, "sub": "machine-1", "username": "bot", "aud": [AUDIENCE]}

    class FakeClient:
        async def post(self, *args, **kwargs):
            calls["count"] += 1
            return FakeResponse()

    async def fake_metadata():
        return {"introspection_endpoint": f"{ISSUER}/oauth/v2/introspect"}

    monkeypatch.setattr(validator, "_get_oidc_metadata", fake_metadata)
    monkeypatch.setattr(validator, "_client", FakeClient)

    user = await validator.validate("opaque-pat-token")
    assert user.sub == "machine-1"
    assert user.name == "bot"

    # Second validation should hit the cache
    await validator.validate("opaque-pat-token")
    assert calls["count"] == 1


async def test_opaque_token_foreign_audience_rejected(monkeypatch):
    config = AuthConfig(
        enabled=True,
        issuer=ISSUER,
        project_id=AUDIENCE,
        introspection_client_id="api-app",
        introspection_client_secret="secret",
        _env_file=None,
    )
    validator = TokenValidator(config)

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            # Active token, but issued for a different client/app in the same Zitadel instance
            return {"active": True, "sub": "machine-2", "aud": ["other-project"], "client_id": "other-app"}

    class FakeClient:
        async def post(self, *args, **kwargs):
            return FakeResponse()

    async def fake_metadata():
        return {"introspection_endpoint": f"{ISSUER}/oauth/v2/introspect"}

    monkeypatch.setattr(validator, "_get_oidc_metadata", fake_metadata)
    monkeypatch.setattr(validator, "_client", FakeClient)

    with pytest.raises(TokenValidationError, match="audience"):
        await validator.validate("opaque-foreign-token")


async def test_inactive_opaque_token_rejected(monkeypatch):
    config = AuthConfig(
        enabled=True,
        issuer=ISSUER,
        project_id=AUDIENCE,
        introspection_client_id="api-app",
        introspection_client_secret="secret",
        _env_file=None,
    )
    validator = TokenValidator(config)

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"active": False}

    class FakeClient:
        async def post(self, *args, **kwargs):
            return FakeResponse()

    async def fake_metadata():
        return {"introspection_endpoint": f"{ISSUER}/oauth/v2/introspect"}

    monkeypatch.setattr(validator, "_get_oidc_metadata", fake_metadata)
    monkeypatch.setattr(validator, "_client", FakeClient)

    with pytest.raises(TokenValidationError, match="not active"):
        await validator.validate("opaque-pat-token")
