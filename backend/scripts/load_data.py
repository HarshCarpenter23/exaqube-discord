"""Idempotent data loader.

Reads the dataset CSVs and inserts them with ON CONFLICT DO NOTHING, so running
it twice never duplicates rows (this is explicitly required, and tested). Row
parsing and type coercion live in scripts/transforms.py; this module handles
reading, batching, and the database writes.

Run: `python -m scripts.load_data`  (or `make load`).
"""

from __future__ import annotations

import asyncio
import csv
import os
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db import models
from app.db.engine import app_engine
from app.logging import configure_logging, get_logger
from scripts import transforms as t

logger = get_logger("load_data")

CHUNK_SIZE = 1000


class TableLoad:
    """How to load one CSV: which model, file, row builder, and conflict key."""

    def __init__(self, model, csv_name: str, builder: Callable[[dict], dict], conflict: list[str]):
        self.model = model
        self.csv_name = csv_name
        self.builder = builder
        self.conflict = conflict


# Loaded in foreign-key order.
LOAD_PLAN = [
    TableLoad(models.Server, "servers.csv", t.server_row, ["server_id"]),
    TableLoad(models.Channel, "channels.csv", t.channel_row, ["channel_id"]),
    TableLoad(models.Member, "members.csv", t.member_row,
              ["server_id", "user_id", "username", "join_date"]),
    TableLoad(models.Message, "messages_sample.csv", t.message_row, ["message_id"]),
    TableLoad(models.DailyStat, "daily_stats.csv", t.daily_stat_row, ["server_id", "day"]),
    TableLoad(models.ChannelDailyStat, "channel_daily_stats.csv", t.channel_daily_stat_row,
              ["channel_id", "day"]),
]


def _read_rows(path: str, builder: Callable[[dict], dict]) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [builder(raw) for raw in csv.DictReader(fh)]


def _chunks(rows: list[Any], size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


async def _load_one(conn, load: TableLoad, data_dir: str) -> int:
    rows = _read_rows(os.path.join(data_dir, load.csv_name), load.builder)
    if rows:
        stmt = pg_insert(load.model).on_conflict_do_nothing(index_elements=load.conflict)
        for chunk in _chunks(rows, CHUNK_SIZE):
            await conn.execute(stmt, chunk)
    total = await conn.scalar(select(func.count()).select_from(load.model))
    logger.info("loaded", table=load.model.__tablename__, read=len(rows), total_in_db=total)
    return total


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("load_start", data_dir=settings.data_dir)

    async with app_engine.begin() as conn:
        for load in LOAD_PLAN:
            await _load_one(conn, load, settings.data_dir)

    await app_engine.dispose()
    logger.info("load_done")


if __name__ == "__main__":
    asyncio.run(run())
