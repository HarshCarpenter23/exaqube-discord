"""Pydantic response models. Endpoints return these, never ORM objects, so the
shape on the wire is explicit and validated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ServerOut(_ORMModel):
    server_id: str
    server_name: str
    region: str | None = None
    approximate_member_count: int | None = None
    creation_date: datetime | None = None


class ChannelOut(_ORMModel):
    channel_id: str
    channel_name: str | None = None
    channel_type: str | None = None
    position: int | None = None


class MemberOut(_ORMModel):
    user_id: str
    username: str | None = None
    display_name: str | None = None
    is_bot: bool
    messages_sent: int | None = None
    join_date: datetime | None = None


class MessageOut(_ORMModel):
    message_id: str
    channel_id: str
    user_id: str
    ts: datetime
    content: str | None = None
    reaction_count: int | None = None


class TimeseriesPoint(BaseModel):
    channel_id: str
    period: datetime
    message_count: int


class Page(BaseModel, Generic[T]):
    """A page of rows plus the paging info the frontend needs."""

    items: list[T]
    total: int
    limit: int
    offset: int


class PinIn(BaseModel):
    title: str | None = None
    spec: dict            # chart encoding: {type, x, y, series, title}
    sql: str


class PinOut(_ORMModel):
    id: str
    title: str | None = None
    spec: dict
    sql: str
    created_at: datetime
