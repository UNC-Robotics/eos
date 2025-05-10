from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from litestar.response import Response
from litestar.connection import Request

from eos.logging.logger import log


class APIError(HTTPException):
    """Base API error with consistent response format."""

    def __init__(self, status_code: int = HTTP_500_INTERNAL_SERVER_ERROR, detail: str = "An unexpected error occurred"):
        super().__init__(status_code=status_code, detail=detail)


def general_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle all exceptions and format into a consistent response."""
    log.error(f"API error: {exc!s}")

    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        detail = exc.detail
    else:
        status_code = HTTP_500_INTERNAL_SERVER_ERROR
        detail = str(exc)

    content = {"error": detail}

    return Response(
        content=content,
        status_code=status_code,
    )
