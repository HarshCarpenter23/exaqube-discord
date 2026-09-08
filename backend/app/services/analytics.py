"""Data-access + aggregation logic for the data endpoints.

Kept separate from the routers (which only handle HTTP) and from the models
(which only describe the schema). All reads go through the read-only session,
so even the frontend's data endpoints exercise the least-privilege path.

The time-series aggregate is computed in the database with date_trunc + GROUP
BY, not in Python.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models

# Buckets we allow for the time-series aggregate. Mapping to a fixed set of
# date_trunc units means the unit is never taken from raw user input.
ALLOWED_BUCKETS = {"hour": "hour", "day": "day", "week": "week"}


async def dataset_now(session: AsyncSession) -> datetime | None:
    """The latest message timestamp in the data. Relative-date questions anchor
    to this instead of wall-clock time, because the dataset runs into the future
    (see docs/01)."""
    return await session.scalar(select(func.max(models.Message.ts)))


async def list_servers(session: AsyncSession) -> list[models.Server]:
    result = await session.scalars(select(models.Server).order_by(models.Server.server_name))
    return list(result)


async def list_channels(session: AsyncSession, server_id: str) -> list[models.Channel]:
    stmt = (
        select(models.Channel)
        .where(models.Channel.server_id == server_id)
        .order_by(models.Channel.position)
    )
    return list(await session.scalars(stmt))


async def list_members(
    session: AsyncSession, server_id: str, limit: int, offset: int
) -> tuple[list[models.Member], int]:
    base = select(models.Member).where(models.Member.server_id == server_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    stmt = base.order_by(models.Member.messages_sent.desc()).limit(limit).offset(offset)
    return list(await session.scalars(stmt)), total or 0


async def list_messages(
    session: AsyncSession,
    server_id: str,
    channel_id: str | None,
    limit: int,
    offset: int,
) -> tuple[list[models.Message], int]:
    base = select(models.Message).where(models.Message.server_id == server_id)
    if channel_id:
        base = base.where(models.Message.channel_id == channel_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    stmt = base.order_by(models.Message.ts.desc()).limit(limit).offset(offset)
    return list(await session.scalars(stmt)), total or 0


async def activity_per_channel_per_day(
    session: AsyncSession,
    server_id: str,
    bucket: str,
    frm: datetime,
    to: datetime,
) -> list[dict]:
    """Time-series aggregate computed in the database: message count per channel
    per time bucket for one server, within [frm, to)."""
    unit = ALLOWED_BUCKETS[bucket]  # validated by the caller; safe to interpolate
    period = func.date_trunc(unit, models.Message.ts).label("period")
    stmt = (
        select(
            models.Message.channel_id.label("channel_id"),
            period,
            func.count().label("message_count"),
        )
        .where(
            models.Message.server_id == server_id,
            models.Message.ts >= frm,
            models.Message.ts < to,
        )
        .group_by(models.Message.channel_id, period)
        .order_by(period)
    )
    rows = await session.execute(stmt)
    return [
        {"channel_id": r.channel_id, "period": r.period, "message_count": r.message_count}
        for r in rows
    ]


def default_window(anchor: datetime, days: int = 90) -> tuple[datetime, datetime]:
    """A sensible default time window ending at the dataset's latest timestamp."""
    return anchor - timedelta(days=days), anchor
