"""Structured JSON logging with a trace ID that follows one request through
the API, the agent, each tool call, and the SQL it runs.

The trace ID lives in a contextvar so any code can log with it without
threading it through every function signature. A middleware sets it per
request; background/agent code inherits it because it runs inside the same
async task.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

import structlog

# Set per request by TraceIDMiddleware; read by the log processor below.
_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id)


def get_trace_id() -> str:
    return _trace_id.get()


def _add_trace_id(_logger, _method, event_dict):
    """structlog processor: stamp every log line with the current trace ID."""
    event_dict["trace_id"] = _trace_id.get()
    return event_dict


def configure_logging(level: str = "info") -> None:
    """Configure structlog to emit JSON lines. Call once at startup."""
    logging.basicConfig(format="%(message)s", level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_trace_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
