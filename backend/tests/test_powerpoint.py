"""Tests for the powerpoint plugin: a real .pptx is produced from a chained
query→chart→deck, and the slide limit is enforced.
"""

from __future__ import annotations

import os
import zipfile

import pytest

from app.agent.loop import AgentLoop
from app.agent.providers.base import TextDelta, ToolCall, TurnDone
from app.artifacts import ArtifactStore
from app.config import get_settings
from app.plugins.base import PluginContext, PluginError, PluginResult
from app.plugins.builtin.powerpoint import PowerPointPlugin
from tests.fake_provider import ScriptedProvider


async def test_chain_query_chart_deck(ro_session, tmp_path):
    store = ArtifactStore(str(tmp_path))
    turns = [
        [ToolCall("query", {"sql": "SELECT channel_id, count(*) AS c FROM messages "
                                   "WHERE server_id='server_007' GROUP BY 1 ORDER BY c DESC LIMIT 5"},
                  "c1"), TurnDone("tool_use")],
        [ToolCall("chart", {"input_ref": "r1", "type": "bar", "x": "channel_id", "y": "c"}, "c2"),
         TurnDone("tool_use")],
        [ToolCall("powerpoint",
                  {"title": "Server 007 Engagement", "summary": "Top channels.",
                   "input_refs": ["r1", "r2"], "slide_headings": ["Top channels", "Chart"]},
                  "c3"), TurnDone("tool_use")],
        [TextDelta("Deck ready."), TurnDone("stop")],
    ]
    events: list = []

    async def emit(stage, payload):
        events.append((stage, payload))

    await AgentLoop(ScriptedProvider(turns), get_settings(), artifacts=store).run(
        "make a deck", ro_session, emit
    )

    artifact = next(p for s, p in events if s == "tool_result" and p["kind"] == "artifact")
    assert artifact["filename"] == "deck.pptx"
    path = store.path_for(artifact["artifact_id"])
    assert os.path.exists(path) and zipfile.is_zipfile(path)   # .pptx is a zip container


async def test_pptx_rejects_too_many_slides(tmp_path):
    store = ArtifactStore(str(tmp_path))
    table = PluginResult(kind="table", data={"columns": ["x"], "rows": [[1]], "row_count": 1}, meta={})
    ctx = PluginContext(
        trace_id="t", ro_session=None, inputs={"input_refs": [table, table]},
        emit=_noop, artifacts=store, row_cap=5000, statement_timeout_ms=5000,
        artifact_max_rows=50_000, artifact_max_bytes=10_000_000, pptx_max_slides=2,
    )
    with pytest.raises(PluginError) as exc:
        await PowerPointPlugin().execute({"title": "X", "input_refs": ["r1", "r2"]}, ctx)
    assert exc.value.code == "too_large"


async def _noop(stage, payload):
    return None
