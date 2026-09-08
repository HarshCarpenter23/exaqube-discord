"""Health endpoint that means something.

/health returns 200 only when the app can actually serve requests: it must
reach the database on both the app role and the read-only agent role. If
either is down, readiness is false and the endpoint returns 503 — which is
what the container healthcheck and compose dependency ordering rely on.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.db.engine import AppSession, ReadOnlySession

router = APIRouter()


async def _can_query(session_factory) -> bool:
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health")
async def health(response: Response) -> dict:
    app_ok = await _can_query(AppSession)
    ro_ok = await _can_query(ReadOnlySession)
    ready = app_ok and ro_ok
    if not ready:
        response.status_code = 503
    return {
        "status": "ok" if ready else "degraded",
        "db": "ok" if app_ok else "unreachable",
        "readonly_role": "ok" if ro_ok else "unreachable",
    }
