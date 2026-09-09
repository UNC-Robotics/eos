from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.middleware import AbstractAuthenticationMiddleware, AuthenticationResult

from eos.auth.identity import record_identity
from eos.auth.token_validator import TokenValidationError, TokenValidator


class EosAuthenticationMiddleware(AbstractAuthenticationMiddleware):
    """Authenticates requests by validating the bearer token against the configured OIDC issuer."""

    async def authenticate_request(self, connection: ASGIConnection) -> AuthenticationResult:
        auth_header = connection.headers.get("Authorization", "")
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise NotAuthorizedException(detail="Missing bearer token")

        validator: TokenValidator = connection.app.state["token_validator"]
        token = token.strip()
        try:
            user = await validator.validate(token)
        except TokenValidationError as e:
            raise NotAuthorizedException(detail=str(e)) from e

        await record_identity(connection.app.state["db_interface"], validator, user, token)

        return AuthenticationResult(user=user, auth=token)
