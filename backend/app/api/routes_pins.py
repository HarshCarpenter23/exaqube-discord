"""Pinned charts.

A pin stores a chart's encoding plus the SQL that produces its rows. The
dashboard lists pins and, for each, re-runs the SQL through the same read-only
safety path the agent uses — so a pinned chart is always live and re-runnable,
not a frozen image.

The SQL is re-validated by the guard before it is stored, so a pin can never
smuggle unsafe SQL, and the re-run executes as the read-only role.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import BadInput, NotFound
from app.api.schemas import PinIn, PinOut
from app.db.engine import get_app_session, get_readonly_session
from app.db.models import Pin
from app.safety.execution import run_readonly_query
from app.safety.sql_guard import SqlNotAllowed, validate
from app.serialization import rows_jsonable
from app.config import get_settings

router = APIRouter(prefix="/api/pins")


@router.post("", response_model=PinOut)
async def create_pin(body: PinIn, session: AsyncSession = Depends(get_app_session)):
    try:
        validate(body.sql)                      # reject unsafe SQL before storing
    except SqlNotAllowed as e:
        raise BadInput(f"Pin SQL rejected: {e}")

    pin = Pin(id=uuid.uuid4().hex, title=body.title, spec=body.spec, sql=body.sql)
    session.add(pin)
    await session.commit()
    await session.refresh(pin)
    return pin


@router.get("", response_model=list[PinOut])
async def list_pins(session: AsyncSession = Depends(get_app_session)):
    result = await session.scalars(select(Pin).order_by(Pin.created_at.desc()))
    return list(result)


@router.delete("/{pin_id}")
async def delete_pin(pin_id: str, session: AsyncSession = Depends(get_app_session)):
    result = await session.execute(delete(Pin).where(Pin.id == pin_id))
    await session.commit()
    if result.rowcount == 0:
        raise NotFound("Pin not found.")
    return {"deleted": pin_id}


@router.get("/{pin_id}/data")
async def pin_data(
    pin_id: str,
    app_session: AsyncSession = Depends(get_app_session),
    ro_session: AsyncSession = Depends(get_readonly_session),
):
    """Re-run a pin's SQL and return fresh rows for the chart."""
    pin = await app_session.get(Pin, pin_id)
    if pin is None:
        raise NotFound("Pin not found.")

    settings = get_settings()
    result = await run_readonly_query(
        ro_session, pin.sql, settings.row_cap, settings.statement_timeout_ms
    )
    return {"columns": result.columns, "rows": rows_jsonable(result.rows)}
