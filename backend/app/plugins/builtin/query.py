"""query plugin — natural language to SQL, executed read-only.

The model writes the SQL directly in its tool call (rather than the plugin
making a second LLM call): it keeps the flow to one model, and the SQL is
visible for streaming and debugging. The plugin's job is to run that SQL safely
and return a structured table other plugins can consume.

This is the source plugin in a chain — it consumes nothing and produces a
`table`.
"""

from __future__ import annotations

from app.plugins.base import Plugin, PluginContext, PluginError, PluginResult
from app.plugins.registry import register
from app.safety.execution import run_readonly_query
from app.safety.sql_guard import SqlNotAllowed


@register
class QueryPlugin(Plugin):
    name = "query"
    description = (
        "Answer a question about the Discord dataset by writing and running a single "
        "read-only SQL SELECT. Use only these tables: servers, channels, members, "
        "messages, daily_stats, channel_daily_stats. Returns a result table that other "
        "tools (chart, excel) can use. Timestamps are UTC; anchor relative dates to the "
        "latest message time, not today."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "A single read-only SQL SELECT statement."},
            "question": {
                "type": "string",
                "description": "The user's question in plain language, for context.",
            },
        },
        "required": ["sql"],
        "additionalProperties": False,
    }
    consumes: set[str] = set()

    async def execute(self, args: dict, ctx: PluginContext) -> PluginResult:
        sql = args["sql"]
        await ctx.emit("tool_progress", {"message": "running query"})
        try:
            result = await run_readonly_query(
                ctx.ro_session, sql, ctx.row_cap, ctx.statement_timeout_ms
            )
        except SqlNotAllowed as e:
            # Rejected by the safety gate. Fixable: the model can rewrite it as a
            # proper read-only SELECT.
            raise PluginError("sql_rejected", str(e), retryable=True) from e
        except Exception as e:
            # e.g. a syntax error or an unknown column. Surface a short, safe
            # message the model can act on; the full error is logged upstream.
            raise PluginError("sql_error", f"Query failed: {str(e)[:200]}", retryable=True) from e

        return PluginResult(
            kind="table",
            data={
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
            },
            meta={"sql": sql, "truncated": result.truncated},
        )
