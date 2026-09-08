"""Run generated SQL safely on the read-only session.

This is the single place generated SQL executes. Both the `query` plugin and
(later) pinned-chart re-runs call it, so the safety guarantees live in one spot:

  - the SQL is validated by sql_guard first (single read statement, allowed
    tables/functions);
  - a per-statement timeout is set as a backstop to the role-level timeout;
  - results are streamed with a server-side cursor and capped at `row_cap`, so
    a query that matches millions of rows can't exhaust memory. One extra row is
    fetched to detect (and report) truncation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.safety.sql_guard import SqlNotAllowed, validate

# Logs carry the current request's trace_id automatically (see app/logging.py),
# so a generated query can be followed from the API down to the SQL.
logger = get_logger("sql")


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    truncated: bool

    @property
    def row_count(self) -> int:
        return len(self.rows)


async def run_readonly_query(
    session: AsyncSession,
    sql: str,
    row_cap: int,
    statement_timeout_ms: int,
) -> QueryResult:
    """Validate and run one read-only query, capped at `row_cap` rows."""
    try:
        validate(sql)  # raises SqlNotAllowed if the statement isn't a safe read
    except SqlNotAllowed as e:
        logger.warning("sql_rejected", reason=str(e), sql=sql)
        raise

    # Backstop timeout for this transaction (the role also has one set).
    # SET LOCAL does not accept bind parameters; the value is an int we control.
    await session.execute(text(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}"))

    started = time.perf_counter()
    result = await session.stream(text(sql))
    try:
        columns = list(result.keys())
        rows: list[list] = []
        async for row in result:
            rows.append(list(row))
            if len(rows) > row_cap:
                break
    finally:
        await result.close()

    truncated = len(rows) > row_cap
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "sql_executed",
        sql=sql,
        rows=len(rows[:row_cap]),
        truncated=truncated,
        duration_ms=duration_ms,
    )
    return QueryResult(columns=columns, rows=rows[:row_cap], truncated=truncated)
