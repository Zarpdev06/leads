from rest_framework.views import exception_handler

from .error_codes import ErrorCode


def custom_exception_handler(exc, context):
    """Uniform error envelope: {detail|errors, code}."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and not isinstance(data.get("detail", None), str):
        payload = {"code": ErrorCode.VALIDATION_ERROR, "errors": data, "detail": "Invalid input."}
    elif isinstance(data, dict) and "detail" in data:
        code = getattr(exc, "default_code", "error")
        payload = {"code": str(code), "detail": str(data["detail"])}
    else:
        payload = {"code": "error", "detail": data}

    response.data = payload
    return response


class DomainError(Exception):
    """Raised by service layers; turned into a 400 by the view."""

    default_code = ErrorCode.DOMAIN_ERROR

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
