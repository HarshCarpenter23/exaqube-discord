"""Shared test fixtures.

`ro_session` yields a read-only session against the running database, and
`make_context` builds a PluginContext around it so plugin integration tests read
the same way the agent runs them.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.plugins import registry
from app.plugins.base import PluginContext

# Register all built-in plugins once for the test session (the app does this at
# startup). Safe to call: Python caches imports, so it won't double-register.
registry.discover()


@pytest_asyncio.fixture
async def ro_session():
    # A fresh engine per test, bound to this test's event loop, so pooled asyncpg
    # connections are never reused across loops (which pytest creates per test).
    engine = create_async_engine(get_settings().readonly_database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _noop_emit(stage: str, payload: dict) -> None:
    return None


def make_context(session, *, row_cap: int = 5000, statement_timeout_ms: int = 5000) -> PluginContext:
    return PluginContext(
        trace_id="test",
        ro_session=session,
        inputs={},
        emit=_noop_emit,
        artifacts=None,
        row_cap=row_cap,
        statement_timeout_ms=statement_timeout_ms,
        artifact_max_rows=50_000,
        artifact_max_bytes=10 * 1024 * 1024,
        pptx_max_slides=20,
    )
