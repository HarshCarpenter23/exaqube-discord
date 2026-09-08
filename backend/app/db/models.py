"""Relational schema for the Discord dataset.

Design notes (see docs/01-data-foundation.md for the full rationale):
  - Timestamps are real timestamps, treated as UTC by convention.
  - `members` uses a surrogate primary key because the dataset's (server_id,
    user_id) pair is NOT actually unique (52 pairs map to two different people),
    despite what the data dictionary claims. The natural key is kept as a
    non-unique column, plus a best-effort uniqueness constraint used only to
    make the load idempotent.
  - Indexes target time-bucketed queries, which dominate this event-log data.
  - `daily_stats` / `channel_daily_stats` are loaded as-is; their member columns
    are known to be unreliable, so the API computes activity from `messages`.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Server(Base):
    __tablename__ = "servers"

    server_id: Mapped[str] = mapped_column(String, primary_key=True)
    server_name: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String)
    creation_date: Mapped[datetime | None] = mapped_column(DateTime)
    region: Mapped[str | None] = mapped_column(String)
    verification_level: Mapped[int | None] = mapped_column(SmallInteger)
    premium_tier: Mapped[int | None] = mapped_column(SmallInteger)
    premium_subscription_count: Mapped[int | None] = mapped_column(Integer)
    approximate_member_count: Mapped[int | None] = mapped_column(Integer)
    approximate_presence_count: Mapped[int | None] = mapped_column(Integer)


class Channel(Base):
    __tablename__ = "channels"

    channel_id: Mapped[str] = mapped_column(String, primary_key=True)
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.server_id"), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String)
    channel_type: Mapped[str | None] = mapped_column(String)   # 'text' | 'voice'
    topic: Mapped[str | None] = mapped_column(Text)
    nsfw: Mapped[bool | None] = mapped_column(Boolean)
    rate_limit_per_user: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_channels_server", "server_id"),)


class Member(Base):
    __tablename__ = "members"

    member_pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.server_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)   # natural key, NOT unique
    username: Mapped[str | None] = mapped_column(String)
    display_name: Mapped[str | None] = mapped_column(String)
    discriminator: Mapped[str | None] = mapped_column(String)
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    join_date: Mapped[datetime | None] = mapped_column(DateTime)
    last_active: Mapped[datetime | None] = mapped_column(DateTime)
    roles: Mapped[str | None] = mapped_column(Text)
    messages_sent: Mapped[int | None] = mapped_column(Integer)
    voice_minutes: Mapped[int | None] = mapped_column(Integer)
    is_owner: Mapped[bool | None] = mapped_column(Boolean)

    __table_args__ = (
        # Best-effort natural key: distinguishes the 52 duplicate (server_id,
        # user_id) pairs (they differ in username/join_date) and gives the loader
        # a conflict target so re-running does not duplicate rows.
        UniqueConstraint("server_id", "user_id", "username", "join_date", name="uq_member_natural"),
        Index("ix_members_server", "server_id"),
    )


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.server_id"), nullable=False)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.channel_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)   # no FK: ambiguous by design
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # renamed from 'timestamp'
    content: Mapped[str | None] = mapped_column(Text)
    has_attachment: Mapped[bool | None] = mapped_column(Boolean)
    has_embed: Mapped[bool | None] = mapped_column(Boolean)
    reaction_count: Mapped[int | None] = mapped_column(Integer)
    is_pinned: Mapped[bool | None] = mapped_column(Boolean)
    length: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_messages_ts", "ts"),
        Index("ix_messages_channel_ts", "channel_id", "ts"),
        Index("ix_messages_server_ts", "server_id", "ts"),
        Index("ix_messages_user", "server_id", "user_id"),
    )


class DailyStat(Base):
    __tablename__ = "daily_stats"

    server_id: Mapped[str] = mapped_column(ForeignKey("servers.server_id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    total_messages: Mapped[int | None] = mapped_column(Integer)
    new_members: Mapped[int | None] = mapped_column(Integer)
    active_members: Mapped[int | None] = mapped_column(Integer)   # unreliable, kept as-is
    total_members: Mapped[int | None] = mapped_column(Integer)    # unreliable, kept as-is
    day_of_week: Mapped[int | None] = mapped_column(SmallInteger)
    is_weekend: Mapped[bool | None] = mapped_column(Boolean)


class ChannelDailyStat(Base):
    __tablename__ = "channel_daily_stats"

    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.channel_id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.server_id"), nullable=False)
    message_count: Mapped[int | None] = mapped_column(Integer)
    active_users: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_cds_server_day", "server_id", "day"),)


class Pin(Base):
    """A pinned chart. App-owned (read/write via the app role, NOT granted to
    agent_ro). Stores the chart encoding plus the SQL that produces its rows, so
    the dashboard can re-run the query and stay live rather than a frozen image."""

    __tablename__ = "pins"

    id: Mapped[str] = mapped_column(String, primary_key=True)          # uuid hex
    title: Mapped[str | None] = mapped_column(String)
    spec: Mapped[dict] = mapped_column(JSONB)                          # {type, x, y, series, title}
    sql: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# Tables the read-only agent role is allowed to read. Used by the migrate step
# to scope grants — pins and any future app-owned tables are deliberately absent.
ANALYTICS_TABLES = [
    "servers",
    "channels",
    "members",
    "messages",
    "daily_stats",
    "channel_daily_stats",
]
