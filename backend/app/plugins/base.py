"""The plugin contract.

Every capability beyond raw SQL is a plugin. The agent core only ever talks to
this interface and the registry — it never names a specific plugin. Adding a
capability means writing one new Plugin subclass in plugins/builtin/; nothing
else in the codebase changes.

A plugin declares:
  - name / description / input_schema  -> used to build the LLM's tool list and prompt
  - consumes                           -> which result kinds it can take as chained input
  - execute()                          -> the actual work

Results are passed between plugins as PluginResult objects (see PluginResult.kind),
which is how "query -> chart -> deck" composes in a single turn.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import jsonschema

from sqlalchemy.ext.asyncio import AsyncSession


class PluginError(Exception):
    """A structured failure a plugin raises. The agent branches on `retryable`
    to decide whether another attempt could help. `message` is safe to show —
    it must never contain a raw stack trace, DSN, or internal path."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code            # e.g. "sql_rejected", "bad_encoding", "too_large"
        self.message = message
        self.retryable = retryable


@dataclass
class PluginResult:
    """What a plugin returns. `kind` decides what downstream plugins may consume
    and how the frontend renders it."""

    kind: str                       # "table" | "chart_spec" | "artifact" | "text"
    data: Any                       # the structured payload for this kind
    meta: dict[str, Any] = field(default_factory=dict)   # e.g. {"sql": ..., "row_count": ...}


@dataclass
class PluginContext:
    """Everything a plugin is handed at execution time — nothing global."""

    trace_id: str
    ro_session: AsyncSession                        # read-only DB session (agent role)
    inputs: dict[str, PluginResult]                 # resolved upstream results, by arg name
    emit: Callable[[str, dict], Awaitable[None]]    # emit(stage, payload) -> stream progress
    artifacts: Any                                  # ArtifactStore (see artifacts module)
    row_cap: int
    statement_timeout_ms: int
    artifact_max_rows: int
    artifact_max_bytes: int
    pptx_max_slides: int


class Plugin(ABC):
    """Base class for every plugin. Subclasses set the class attributes and
    implement execute(). validate() is provided and checks the LLM's arguments
    against input_schema before execute() runs."""

    name: str
    description: str
    input_schema: dict[str, Any]
    consumes: set[str] = set()      # result kinds this plugin can take as input

    def validate(self, args: dict[str, Any]) -> dict[str, Any]:
        """Validate args against input_schema. Raises PluginError so the agent
        can see a structured, retryable error rather than a raw exception."""
        try:
            jsonschema.validate(args, self.input_schema)
        except jsonschema.ValidationError as e:
            raise PluginError("invalid_args", e.message, retryable=True) from e
        return args

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: PluginContext) -> PluginResult:
        ...
