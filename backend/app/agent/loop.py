"""The agent loop.

Runs the model, executes the tools it calls, feeds results back, and repeats
until the model answers in prose or the step limit is hit (graceful surrender).
It is generic across plugins: it only uses the registry and the provider, and
never names a specific plugin.

Behaviours (docs/04):
  - Query: the model calls `query`; we run it and feed back a small preview.
  - Recover: a failed tool returns a structured error the model can see and fix
    on its next step (bounded by the step limit).
  - Decline: the model may answer "I can't answer that from this dataset".
  - Chain: results are stored under handles (r1, r2, ...); the model references a
    handle to feed one tool's output into the next.

Only a compact preview of a result is sent back to the model (columns + a few
rows). The full result stays server-side in `results` for downstream plugins —
this keeps token usage within the free-tier budget and limits what untrusted row
content can influence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompt import build_system_prompt
from app.agent.providers.base import (
    LLMProvider,
    Message,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolCallRef,
    TurnDone,
)
from app.config import Settings
from app.logging import get_logger
from app.plugins import registry
from app.plugins.base import PluginContext, PluginError, PluginResult
from app.serialization import rows_jsonable
from app.services.analytics import dataset_now

logger = get_logger("agent.loop")

Emit = Callable[[str, dict], Awaitable[None]]


@dataclass
class _Rendered:
    """A tool result rendered two ways: a compact string for the model, and a
    richer payload for the frontend to display."""

    for_model: str
    for_client: dict


class AgentLoop:
    def __init__(self, provider: LLMProvider, settings: Settings, artifacts: Any):
        self._provider = provider
        self._settings = settings
        self._artifacts = artifacts

    async def run(self, user_message: str, ro_session: AsyncSession, emit: Emit) -> None:
        plugins = registry.all_plugins()
        system = build_system_prompt(plugins, await dataset_now(ro_session))
        tools = registry.tool_schemas()

        messages: list[Message] = [Message(role="user", content=user_message)]
        results: dict[str, PluginResult] = {}
        handle_seq = 0

        for _step in range(self._settings.agent_max_steps):
            assistant_text, tool_calls = await self._one_turn(messages, tools, system, emit)

            if not tool_calls:
                await emit("done", {"handles": list(results)})
                return

            messages.append(
                Message(
                    role="assistant",
                    content=assistant_text,
                    tool_calls=[ToolCallRef(tc.call_id, tc.name, tc.args) for tc in tool_calls],
                )
            )

            for tc in tool_calls:
                handle_seq += 1
                handle = f"r{handle_seq}"
                await emit("tool_selected", {"name": tc.name, "args": tc.args, "handle": handle})
                content = await self._run_tool(tc, handle, results, ro_session, emit)
                messages.append(Message(role="tool", tool_call_id=tc.call_id, content=content))

        # Ran out of steps.
        await emit("done", {"handles": list(results), "note": "reached step limit"})

    async def _one_turn(
        self, messages: list[Message], tools: list[dict], system: str, emit: Emit
    ) -> tuple[str, list[ToolCall]]:
        """Stream one model turn, forwarding stage events. Returns the prose text
        and any tool calls the model made."""
        assistant_text = ""
        tool_calls: list[ToolCall] = []
        try:
            async for ev in self._provider.stream(messages, tools, system):
                if isinstance(ev, ReasoningDelta):
                    await emit("reasoning", {"delta": ev.text})
                elif isinstance(ev, TextDelta):
                    assistant_text += ev.text
                    await emit("message", {"delta": ev.text})
                elif isinstance(ev, ToolCall):
                    tool_calls.append(ev)
                elif isinstance(ev, TurnDone):
                    break
        except Exception as e:
            logger.exception("provider_error")
            await emit("error", {"code": "provider_error", "message": str(e)[:200]})
        return assistant_text, tool_calls

    async def _run_tool(
        self,
        tc: ToolCall,
        handle: str,
        results: dict[str, PluginResult],
        ro_session: AsyncSession,
        emit: Emit,
    ) -> str:
        """Execute one tool call. Returns the string to feed back to the model.
        All failures become a structured message the model can recover from."""
        try:
            plugin = registry.get(tc.name)
        except KeyError:
            await emit("tool_error", {"handle": handle, "code": "unknown_tool", "message": tc.name})
            return f"ERROR [unknown_tool]: no tool named {tc.name!r}."

        try:
            args = plugin.validate(tc.args)
            inputs = self._resolve_inputs(args, plugin.consumes, results)
            ctx = self._make_context(ro_session, inputs, emit)
            result = await plugin.execute(args, ctx)
        except PluginError as e:
            await emit("tool_error", {
                "handle": handle, "code": e.code, "message": e.message, "retryable": e.retryable,
            })
            return f"ERROR [{e.code}]: {e.message}" + (" (you may fix and retry)" if e.retryable else "")

        results[handle] = result
        rendered = self._render(handle, result)
        await emit("tool_result", {"handle": handle, "kind": result.kind, **rendered.for_client})
        return rendered.for_model

    def _resolve_inputs(
        self, args: dict, consumes: set[str], results: dict[str, PluginResult]
    ) -> dict[str, PluginResult]:
        """Resolve handle references in the args (input_ref / input_refs) into the
        actual prior results, and check they are a kind this plugin consumes."""
        inputs: dict[str, Any] = {}

        def resolve_one(handle: str) -> PluginResult:
            if handle not in results:
                raise PluginError("bad_reference", f"No result with handle {handle!r}.", retryable=True)
            prior = results[handle]
            if consumes and prior.kind not in consumes:
                raise PluginError(
                    "bad_reference",
                    f"Handle {handle!r} is a {prior.kind}, but this tool consumes {sorted(consumes)}.",
                    retryable=True,
                )
            return prior

        if "input_ref" in args:
            inputs["input_ref"] = resolve_one(args["input_ref"])
        if "input_refs" in args:
            inputs["input_refs"] = [resolve_one(h) for h in args["input_refs"]]
        return inputs

    def _make_context(self, ro_session, inputs, emit: Emit) -> PluginContext:
        s = self._settings
        return PluginContext(
            trace_id="-",
            ro_session=ro_session,
            inputs=inputs,
            emit=emit,
            artifacts=self._artifacts,
            row_cap=s.row_cap,
            statement_timeout_ms=s.statement_timeout_ms,
            artifact_max_rows=s.artifact_max_rows,
            artifact_max_bytes=s.artifact_max_bytes,
            pptx_max_slides=s.pptx_max_slides,
        )

    def _render(self, handle: str, result: PluginResult) -> _Rendered:
        """Render a result compactly for the model and richly for the client."""
        if result.kind == "table":
            cols = result.data["columns"]
            n = result.data["row_count"]
            preview = rows_jsonable(result.data["rows"], self._settings.result_preview_rows)
            trunc = " (truncated at row cap)" if result.meta.get("truncated") else ""
            for_model = (
                f"handle {handle} (table): columns={cols}; row_count={n}{trunc}; "
                f"sample_rows={preview}"
            )
            return _Rendered(for_model, {
                "columns": cols, "rows": preview, "row_count": n,
                "truncated": result.meta.get("truncated", False), "sql": result.meta.get("sql"),
            })

        if result.kind == "artifact":
            d = result.data
            for_model = f"handle {handle} (artifact): {d['filename']} ready at {d['url']}."
            return _Rendered(for_model, dict(d))

        if result.kind == "chart_spec":
            for_model = f"handle {handle} (chart_spec): {result.data.get('type')} chart shown to the user."
            return _Rendered(for_model, dict(result.data))

        # text or anything else
        text = str(result.data)
        return _Rendered(f"handle {handle}: {text}", {"text": text})
