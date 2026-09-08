"""Groq provider (OpenAI-compatible chat completions).

Streams one model turn: reasoning and prose tokens are yielded as they arrive,
and tool calls are assembled from their streamed fragments and yielded once
complete. Translating our provider-neutral Message objects to/from OpenAI's
wire format is this class's job — the agent loop never sees Groq specifics.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from groq import AsyncGroq

from app.agent.providers.base import (
    LLMProvider,
    Message,
    ProviderEvent,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    TurnDone,
)


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}


def _to_openai_messages(system: str, messages: list[Message]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or "",
                    "tool_calls": [
                        {
                            "id": tc.call_id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
        elif m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, max_completion_tokens: int):
        self._client = AsyncGroq(api_key=api_key)
        self._model = model
        self._max_tokens = max_completion_tokens

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict],
        system: str,
    ) -> AsyncIterator[ProviderEvent]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=_to_openai_messages(system, messages),
            tools=_to_openai_tools(tools) or None,
            stream=True,
            temperature=0,
            max_completion_tokens=self._max_tokens,
        )

        # Tool calls arrive in fragments keyed by index; accumulate then emit.
        tool_acc: dict[int, dict] = {}

        async for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta

            reasoning = getattr(delta, "reasoning", None)
            if reasoning:
                yield ReasoningDelta(reasoning)
            if delta.content:
                yield TextDelta(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = tool_acc.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments

            if choice.finish_reason:
                for slot in tool_acc.values():
                    yield ToolCall(
                        name=slot["name"], args=_safe_json(slot["args"]), call_id=slot["id"]
                    )
                yield TurnDone(stop_reason=choice.finish_reason)
                return
