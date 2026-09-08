"""LLM provider abstraction.

The agent loop talks to this interface, never to a specific SDK. The default
implementation is Groq (groq_provider.py); any other provider is a new file
implementing LLMProvider, selected by the LLM_PROVIDER env var.

`stream()` yields small events as they arrive so the agent can forward the
agent's reasoning, tool choices, and prose to the UI in real time. The provider
is responsible only for talking to the model — executing tools and looping is
the agent's job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


# --- Messages exchanged with the model -------------------------------------

@dataclass
class ToolCallRef:
    """A tool call the model made, recorded on an assistant message so it can be
    replayed to the provider on the next turn."""

    call_id: str
    name: str
    args: dict[str, Any]


@dataclass
class Message:
    role: str                              # "user" | "assistant" | "tool"
    content: str = ""                      # text content
    tool_calls: list[ToolCallRef] | None = None   # on an assistant tool-use turn
    tool_call_id: str | None = None        # on a role="tool" result message


# --- Streamed events out of the provider -----------------------------------

@dataclass
class ReasoningDelta:
    text: str


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    call_id: str


@dataclass
class TurnDone:
    stop_reason: str                # "end_turn" | "tool_use" | ...


ProviderEvent = ReasoningDelta | TextDelta | ToolCall | TurnDone


class LLMProvider(ABC):
    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        tools: list[dict],
        system: str,
    ) -> AsyncIterator[ProviderEvent]:
        """Stream one model turn given the conversation, tool schemas, and the
        system prompt. Yields ProviderEvents until a TurnDone."""
        ...
