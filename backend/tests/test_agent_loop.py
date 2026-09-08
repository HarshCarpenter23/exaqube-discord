"""Agent loop tests using a scripted provider (no real model calls).

These prove the four required behaviours — query, chain, recover, decline —
against the real database and real plugins, with the model's decisions scripted.
"""

from __future__ import annotations

from app.agent.loop import AgentLoop
from app.agent.providers.base import TextDelta, ToolCall, TurnDone
from app.config import get_settings
from tests.fake_provider import ScriptedProvider


def _collect():
    events: list[tuple[str, dict]] = []

    async def emit(stage: str, payload: dict) -> None:
        events.append((stage, payload))

    return events, emit


def _loop(turns):
    return AgentLoop(ScriptedProvider(turns), get_settings(), artifacts=None)


async def test_query_then_answer(ro_session):
    turns = [
        [ToolCall("query", {"sql": "SELECT count(*) AS c FROM servers"}, "c1"), TurnDone("tool_use")],
        [TextDelta("There are 10 servers."), TurnDone("stop")],
    ]
    events, emit = _collect()
    await _loop(turns).run("How many servers are there?", ro_session, emit)

    stages = [s for s, _ in events]
    assert "tool_selected" in stages
    assert "tool_result" in stages
    assert "done" in stages
    # the query result came back as a table
    result = next(p for s, p in events if s == "tool_result")
    assert result["kind"] == "table"
    assert result["rows"] == [[10]]


async def test_decline_without_tool(ro_session):
    turns = [[TextDelta("I can't answer that from this dataset."), TurnDone("stop")]]
    events, emit = _collect()
    await _loop(turns).run("What's the weather?", ro_session, emit)

    stages = [s for s, _ in events]
    assert "tool_selected" not in stages
    assert "done" in stages


async def test_chain_query_to_chart(ro_session):
    turns = [
        [ToolCall("query",
                  {"sql": "SELECT date_trunc('day', ts) AS day, count(*) AS c FROM messages "
                          "WHERE server_id = 'server_007' GROUP BY 1 ORDER BY 1"},
                  "c1"), TurnDone("tool_use")],
        [ToolCall("chart", {"input_ref": "r1", "type": "line", "x": "day", "y": "c"}, "c2"),
         TurnDone("tool_use")],
        [TextDelta("Here is the activity chart."), TurnDone("stop")],
    ]
    events, emit = _collect()
    await _loop(turns).run("Chart daily activity for server_007", ro_session, emit)

    kinds = [p["kind"] for s, p in events if s == "tool_result"]
    assert kinds == ["table", "chart_spec"]
    chart = next(p for s, p in events if s == "tool_result" and p["kind"] == "chart_spec")
    assert chart["type"] == "line" and chart["x"] == "day" and chart["y"] == "c"
    assert chart["sql"]              # spec carries its query -> re-runnable
    assert len(chart["rows"]) >= 1


async def test_chart_bad_column_is_recoverable(ro_session):
    turns = [
        [ToolCall("query", {"sql": "SELECT channel_id, count(*) AS c FROM messages GROUP BY 1"},
                  "c1"), TurnDone("tool_use")],
        [ToolCall("chart", {"input_ref": "r1", "type": "line", "x": "nope", "y": "c"}, "c2"),
         TurnDone("tool_use")],
        [TextDelta("Let me correct that."), TurnDone("stop")],
    ]
    events, emit = _collect()
    await _loop(turns).run("chart it", ro_session, emit)

    errors = [p for s, p in events if s == "tool_error"]
    assert errors and errors[0]["code"] == "bad_encoding"
    assert errors[0]["retryable"] is True


async def test_recover_from_rejected_sql(ro_session):
    turns = [
        [ToolCall("query", {"sql": "DROP TABLE servers"}, "c1"), TurnDone("tool_use")],
        [TextDelta("Sorry, I can only read data."), TurnDone("stop")],
    ]
    events, emit = _collect()
    await _loop(turns).run("Delete the servers", ro_session, emit)

    errors = [p for s, p in events if s == "tool_error"]
    assert errors and errors[0]["code"] == "sql_rejected"
    assert errors[0]["retryable"] is True
    assert "done" in [s for s, _ in events]
