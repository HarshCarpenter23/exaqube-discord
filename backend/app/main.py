"""FastAPI application factory.

Wires together config, logging, the trace-ID middleware, error handlers, and
the routers. Startup validates that the chosen LLM provider is usable, so a
misconfigured deployment fails here rather than on the first chat request.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.errors import register_error_handlers
from app.api.routes_artifacts import router as artifacts_router
from app.api.routes_chat import router as chat_router
from app.api.routes_data import router as data_router
from app.api.routes_health import router as health_router
from app.api.routes_pins import router as pins_router
from app.config import get_settings
from app.db.engine import dispose_engines
from app.logging import configure_logging, get_logger, new_trace_id, set_trace_id
from app.plugins import registry

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging(settings.log_level)
    settings.require_provider_key()  # fail loud on missing key
    registry.discover()              # load plugins from plugins/builtin/
    get_logger("app").info(
        "startup",
        provider=settings.llm_provider,
        model=settings.llm_model,
        plugins=[p.name for p in registry.all_plugins()],
    )
    yield
    await dispose_engines()


def create_app() -> FastAPI:
    app = FastAPI(title="Exaqube Discord Analytics", lifespan=lifespan)

    @app.middleware("http")
    async def trace_id_middleware(request: Request, call_next):
        # Honor an incoming trace ID (e.g. from the frontend), else make one.
        trace_id = request.headers.get("x-trace-id") or new_trace_id()
        set_trace_id(trace_id)
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(data_router)
    app.include_router(chat_router)
    app.include_router(artifacts_router)
    app.include_router(pins_router)
    return app


app = create_app()
