"""Consistent error envelope.

Every error response has the same shape so the frontend can handle them
uniformly, and the wire never carries a stack trace or a raw 500 body:

    {"error": {"code", "message", "trace_id", "details"}}

Two app-level exceptions cover the common cases (bad input, not found). Any
unexpected exception is logged with its trace ID and returned as a generic
500 envelope.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.logging import get_logger, get_trace_id

logger = get_logger("api.errors")


class AppError(Exception):
    """Base for expected, client-facing errors."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BadInput(AppError):
    status_code = 400
    code = "invalid_request"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


def _envelope(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "trace_id": get_trace_id(),
            "details": details or {},
        }
    }
    return JSONResponse(status_code=status, content=body)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError):
        return _envelope(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_request: Request, exc: RequestValidationError):
        return _envelope(422, "validation_error", "Invalid request.", {"errors": exc.errors()})

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception):
        # Log the real error (with trace ID); return a generic message only.
        logger.exception("unhandled_error", error=str(exc))
        return _envelope(500, "internal_error", "An unexpected error occurred.")
