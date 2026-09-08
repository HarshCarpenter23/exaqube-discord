"""Helpers to turn database values (datetimes, dates, Decimals) into
JSON-serializable forms. Used wherever result rows cross a JSON boundary — the
SSE stream, chart specs, and artifacts.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def rows_jsonable(rows: list[list], limit: int | None = None) -> list[list]:
    selected = rows[:limit] if limit is not None else rows
    return [[jsonable(v) for v in row] for row in selected]
