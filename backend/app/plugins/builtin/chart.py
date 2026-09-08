"""chart plugin — turns a result table into a chart spec.

Returns a spec (chart type + encoding + the rows + the SQL that produced them),
not a rendered image. The frontend draws it, and because the spec carries its
SQL the chart stays re-runnable — which is what makes pinning meaningful.

Consumes a `table` (from the query plugin) via an input_ref handle.
"""

from __future__ import annotations

from app.plugins.base import Plugin, PluginContext, PluginError, PluginResult
from app.plugins.registry import register
from app.serialization import rows_jsonable

_CHART_TYPES = ["line", "bar", "distribution"]


@register
class ChartPlugin(Plugin):
    name = "chart"
    description = (
        "Turn a result table into a chart. Types: line (time series), bar (top-N), "
        "distribution (histogram). Pass input_ref to the table's handle and the column "
        "names to plot. Time series is the common case."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "input_ref": {"type": "string", "description": "Handle of the table to chart."},
            "type": {"type": "string", "enum": _CHART_TYPES},
            "x": {"type": "string", "description": "Column for the x-axis (or the values to bin)."},
            "y": {"type": "string", "description": "Column for the y-axis (numeric)."},
            "series": {"type": "string", "description": "Optional column to split series by."},
            "title": {"type": "string"},
        },
        "required": ["input_ref", "type", "x"],
        "additionalProperties": False,
    }
    consumes = {"table"}

    async def execute(self, args: dict, ctx: PluginContext) -> PluginResult:
        table = ctx.inputs["input_ref"]              # resolved + kind-checked by the loop
        columns = table.data["columns"]

        self._require_column(args["x"], columns)
        if args["type"] != "distribution":
            if "y" not in args:
                raise PluginError("bad_encoding", "A line/bar chart needs a 'y' column.", retryable=True)
            self._require_column(args["y"], columns)
        if args.get("series"):
            self._require_column(args["series"], columns)

        spec = {
            "type": args["type"],
            "x": args["x"],
            "y": args.get("y"),
            "series": args.get("series"),
            "title": args.get("title"),
            "columns": columns,
            "rows": rows_jsonable(table.data["rows"]),
            "sql": table.meta.get("sql"),          # keeps the chart re-runnable
        }
        return PluginResult(kind="chart_spec", data=spec, meta={})

    def _require_column(self, name: str, columns: list[str]) -> None:
        if name not in columns:
            raise PluginError(
                "bad_encoding",
                f"Column {name!r} is not in the result (have: {columns}).",
                retryable=True,
            )
