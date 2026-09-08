"""Tests for the excel plugin: a real workbook is produced and downloadable, and
the oversize bound rejects an export that's too large.
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
from app.plugins.builtin.excel import ExcelPlugin
from tests.fake_provider import ScriptedProvider


async def test_chain_query_to_excel(ro_session, tmp_path):
    store = ArtifactStore(str(tmp_path))
    turns = [
        [ToolCall("query", {"sql": "SELECT server_id, server_name FROM servers"}, "c1"),
         TurnDone("tool_use")],
        [ToolCall("excel", {"input_refs": ["r1"], "sheet_names": ["Servers"], "filename": "servers"},
                  "c2"), TurnDone("tool_use")],
        [TextDelta("Workbook ready."), TurnDone("stop")],
    ]
    events: list = []

    async def emit(stage, payload):
        events.append((stage, payload))

    await AgentLoop(ScriptedProvider(turns), get_settings(), artifacts=store).run(
        "export the servers", ro_session, emit
    )

    artifact = next(p for s, p in events if s == "tool_result" and p["kind"] == "artifact")
    assert artifact["filename"] == "servers.xlsx"
    path = store.path_for(artifact["artifact_id"])
    assert os.path.exists(path)
    assert zipfile.is_zipfile(path)   # a real .xlsx is a zip container


async def test_excel_rejects_oversize(tmp_path):
    store = ArtifactStore(str(tmp_path))
    table = PluginResult(kind="table", data={"columns": ["x"], "rows": [[1]], "row_count": 100}, meta={})
    ctx = PluginContext(
        trace_id="t", ro_session=None, inputs={"input_refs": [table]},
        emit=_noop, artifacts=store, row_cap=5000, statement_timeout_ms=5000,
        artifact_max_rows=10, artifact_max_bytes=10_000_000, pptx_max_slides=20,
    )
    with pytest.raises(PluginError) as exc:
        await ExcelPlugin().execute({"input_refs": ["r1"]}, ctx)
    assert exc.value.code == "too_large"


async def _noop(stage, payload):
    return None
