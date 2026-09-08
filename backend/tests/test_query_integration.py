"""Integration tests for the query plugin against the real database.

Proves the full read path: valid SQL returns a structured table, rejected SQL
surfaces a structured PluginError (not a crash), and the row cap actually
truncates so a large result can't run away.
"""

import pytest

from app.plugins.base import PluginError
from app.plugins.builtin.query import QueryPlugin
from tests.conftest import make_context

plugin = QueryPlugin()


async def test_valid_query_returns_table(ro_session):
    ctx = make_context(ro_session)
    result = await plugin.execute(
        {"sql": "SELECT channel_id, count(*) AS c FROM messages "
                "WHERE server_id = 'server_001' GROUP BY channel_id ORDER BY c DESC LIMIT 5"},
        ctx,
    )
    assert result.kind == "table"
    assert result.data["columns"] == ["channel_id", "c"]
    assert result.data["row_count"] >= 1
    assert result.meta["truncated"] is False


async def test_rejected_sql_raises_structured_error(ro_session):
    ctx = make_context(ro_session)
    with pytest.raises(PluginError) as exc:
        await plugin.execute({"sql": "DROP TABLE messages"}, ctx)
    assert exc.value.code == "sql_rejected"


async def test_row_cap_truncates(ro_session):
    ctx = make_context(ro_session, row_cap=5)
    result = await plugin.execute({"sql": "SELECT message_id FROM messages"}, ctx)
    assert result.data["row_count"] == 5
    assert result.meta["truncated"] is True
