"""Application errors and the consistent error envelope. Stdlib only."""
from __future__ import annotations

from typing import Any, List, Optional


class AppError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, details: Optional[List[Any]] = None, code: Optional[str] = None,
                 status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.details = details or []
        if code:
            self.code = code
        if status:
            self.status = status

    def envelope(self) -> dict:
        return error_envelope(self.code, self.message, self.details)


class ValidationFailed(AppError):
    status = 422
    code = "validation_error"


class Unauthorized(AppError):
    status = 401
    code = "unauthorized"


class Forbidden(AppError):
    status = 403
    code = "forbidden"


class NotFound(AppError):
    status = 404
    code = "not_found"


class Conflict(AppError):
    status = 409
    code = "conflict"


class PayloadTooLarge(AppError):
    status = 413
    code = "payload_too_large"


class TooManyRequests(AppError):
    status = 429
    code = "rate_limited"

    def __init__(self, message: str = "rate limit exceeded", retry_after: float = 1.0):
        super().__init__(message)
        self.retry_after = retry_after


def error_envelope(code: str, message: str, details: Optional[List[Any]] = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}
