"""Create the schema and the read-only agent role. Idempotent: safe to run
repeatedly (compose runs it on every `up`).

Two responsibilities:
  1. Create all tables from the SQLAlchemy models (checkfirst — no-op if they
     already exist).
  2. Create the `agent_ro` login role and scope its grants to SELECT on the
     analytics tables only, with a statement timeout and read-only transactions.
     This is the database-level half of the safety story: the agent connects as
     this role, so writes are impossible regardless of what SQL it generates.

Runs as the app/owner role, which is a superuser in the postgres image and can
therefore create roles and grant privileges.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.config import get_settings
from app.db.engine import app_engine
from app.db.models import ANALYTICS_TABLES, Base
from app.logging import configure_logging, get_logger

logger = get_logger("migrate")


def _role_sql(password: str, timeout_ms: int) -> list[str]:
    """SQL statements to (idempotently) create and scope the read-only role.
    The password comes from config; single quotes are escaped defensively."""
    safe_pw = password.replace("'", "''")
    grant_targets = ", ".join(ANALYTICS_TABLES)
    return [
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_ro') THEN
                CREATE ROLE agent_ro LOGIN PASSWORD '{safe_pw}';
            END IF;
        END
        $$;
        """,
        "GRANT USAGE ON SCHEMA public TO agent_ro;",
        f"GRANT SELECT ON {grant_targets} TO agent_ro;",
        f"ALTER ROLE agent_ro SET statement_timeout = '{int(timeout_ms)}';",
        "ALTER ROLE agent_ro SET default_transaction_read_only = on;",
    ]


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("schema_ready", tables=len(Base.metadata.tables))

        for statement in _role_sql(settings.agent_ro_password, settings.statement_timeout_ms):
            await conn.execute(text(statement))
        logger.info("readonly_role_ready", role="agent_ro", grants=ANALYTICS_TABLES)

    await app_engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
