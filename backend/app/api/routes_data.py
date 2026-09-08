"""Data endpoints that power the frontend.

Routers do HTTP only: validate inputs, call the analytics service, shape the
response. All reads use the read-only session.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import BadInput
from app.api.schemas import ChannelOut, MemberOut, MessageOut, Page, ServerOut, TimeseriesPoint
from app.db.engine import get_readonly_session
from app.services import analytics

router = APIRouter(prefix="/api")


@router.get("/meta")
async def meta(session: AsyncSession = Depends(get_readonly_session)) -> dict:
    """Small metadata the frontend and agent use — notably the dataset's latest
    timestamp, which relative-date queries anchor to."""
    return {"dataset_now": await analytics.dataset_now(session)}


@router.get("/servers", response_model=list[ServerOut])
async def get_servers(session: AsyncSession = Depends(get_readonly_session)):
    return await analytics.list_servers(session)


@router.get("/channels", response_model=list[ChannelOut])
async def get_channels(
    server_id: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_readonly_session),
):
    return await analytics.list_channels(session, server_id)


@router.get("/members", response_model=Page[MemberOut])
async def get_members(
    server_id: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_readonly_session),
):
    items, total = await analytics.list_members(session, server_id, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/messages", response_model=Page[MessageOut])
async def get_messages(
    server_id: str = Query(..., min_length=1),
    channel_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_readonly_session),
):
    items, total = await analytics.list_messages(session, server_id, channel_id, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/timeseries/activity", response_model=list[TimeseriesPoint])
async def get_activity(
    server_id: str = Query(..., min_length=1),
    bucket: str = Query("day"),
    frm: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    session: AsyncSession = Depends(get_readonly_session),
):
    if bucket not in analytics.ALLOWED_BUCKETS:
        raise BadInput(
            f"Unknown bucket {bucket!r}.",
            {"allowed": sorted(analytics.ALLOWED_BUCKETS)},
        )

    anchor = await analytics.dataset_now(session)
    if anchor is None:
        return []  # no data loaded yet

    if frm is None or to is None:
        default_from, default_to = analytics.default_window(anchor)
        frm = frm or default_from
        to = to or default_to
    if frm >= to:
        raise BadInput("`from` must be earlier than `to`.")

    return await analytics.activity_per_channel_per_day(session, server_id, bucket, frm, to)
