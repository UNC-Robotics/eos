from functools import wraps

from litestar import Response, status_codes, Request

from eos.logging.logger import log


class AppError(Exception):
    def __init__(
        self, message: str, status_code: int = status_codes.HTTP_500_INTERNAL_SERVER_ERROR, expose_message: bool = False
    ):
        self.message = message
        self.status_code = status_code
        self.expose_message = expose_message


def handle_exceptions(error_msg: str) -> callable:
    def decorator(func: callable) -> callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Response:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                raise AppError(f"{error_msg}: {e!s}", expose_message=True) from e

        return wrapper

    return decorator


def global_exception_handler(request: Request, exc: Exception) -> Response:
    log.error(f"Web API error: {exc!s}")
    if isinstance(exc, AppError):
        content = {"message": exc.message} if exc.expose_message else {"message": "An error occurred"}
        return Response(content=content, status_code=exc.status_code)

    # For any other exception, return a generic error message
    return Response(
        content={"message": "An unexpected error occurred"}, status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR
    )
