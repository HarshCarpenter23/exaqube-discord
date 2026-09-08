"""Async database access.

Two engines on purpose:
  - `app` engine  -> app role, read/write on app-owned tables (e.g. pins).
  - `readonly` engine -> the agent's read-only role. The agent's generated SQL
    only ever runs here, so write access is impossible even if every other
    check failed. This is the database-level half of the safety story.

Sessions are handed out as FastAPI dependencies so each request gets one and
it is closed for it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_settings = get_settings()

app_engine: AsyncEngine = create_async_engine(
    _settings.database_url, pool_pre_ping=True
)
readonly_engine: AsyncEngine = create_async_engine(
    _settings.readonly_database_url, pool_pre_ping=True
)

AppSession = async_sessionmaker(app_engine, expire_on_commit=False)
ReadOnlySession = async_sessionmaker(readonly_engine, expire_on_commit=False)


async def get_app_session() -> AsyncIterator[AsyncSession]:
    """Dependency: a read/write session on app-owned tables."""
    async with AppSession() as session:
        yield session


async def get_readonly_session() -> AsyncIterator[AsyncSession]:
    """Dependency: a read-only session for agent SQL and pin re-runs."""
    async with ReadOnlySession() as session:
        yield session


async def dispose_engines() -> None:
    """Close both connection pools on shutdown."""
    await app_engine.dispose()
    await readonly_engine.dispose()
