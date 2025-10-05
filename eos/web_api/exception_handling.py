from litestar.exceptions import HTTPException, ValidationException
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from litestar.response import Response
from litestar.connection import Request
from pydantic import ValidationError

from eos.logging.logger import log


class APIError(HTTPException):
    """Base API error with consistent response format."""

    def __init__(self, status_code: int = HTTP_500_INTERNAL_SERVER_ERROR, detail: str = "An unexpected error occurred"):
        super().__init__(status_code=status_code, detail=detail)


def _format_pydantic_errors(errors: list[dict]) -> list[str]:
    """Format Pydantic validation errors into readable messages."""
    formatted = []
    for e in errors:
        loc = e.get("loc", ())
        msg = e.get("msg", "")
        field = ".".join(str(x) for x in loc) if loc else "body"
        if field and msg:
            formatted.append(f"{field}: {msg}")
    return formatted


def _format_litestar_errors(errors: list[dict]) -> list[str]:
    """Format Litestar validation errors into readable messages."""
    formatted = []
    for e in errors:
        if isinstance(e, dict):
            key = e.get("key", "body")
            message = e.get("message", "")
            if key and message:
                formatted.append(f"{key}: {message}")
    return formatted


def general_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle all exceptions and format into a consistent response."""
    # Validation errors
    if isinstance(exc, ValidationError):
        error_details = _format_pydantic_errors(exc.errors())
        detail = "; ".join(error_details) if error_details else str(exc)
        log.error(f"API error: {request.method} {request.url.path}: {detail}")
        return Response(content={"error": detail}, status_code=400)

    if isinstance(exc, ValidationException):
        error_details = []
        if hasattr(exc, "extra") and isinstance(exc.extra, list):
            error_details = _format_litestar_errors(exc.extra)

        detail = "; ".join(error_details) if error_details else (exc.detail or str(exc))
        log.error(f"API error: {request.method} {request.url.path}: {detail}")
        return Response(content={"error": detail}, status_code=400)

    # Other HTTP and general exceptions
    log.error(f"API error: {exc!s}")
    status_code = exc.status_code if isinstance(exc, HTTPException) else HTTP_500_INTERNAL_SERVER_ERROR
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)

    return Response(content={"error": detail}, status_code=status_code)
