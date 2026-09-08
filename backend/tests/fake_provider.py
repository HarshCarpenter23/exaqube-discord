"""A scripted LLM provider for tests.

Given a list of turns (each a list of provider events), it replays one turn per
stream() call. This lets us test the agent loop's routing, chaining, recovery,
and decline behaviour deterministically, without calling a real model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.agent.providers.base import LLMProvider, Message, ProviderEvent


class ScriptedProvider(LLMProvider):
    def __init__(self, turns: list[list[ProviderEvent]]):
        self._turns = turns
        self._i = 0

    async def stream(
        self, messages: list[Message], tools: list[dict], system: str
    ) -> AsyncIterator[ProviderEvent]:
        turn = self._turns[self._i]
        self._i += 1
        for event in turn:
            yield event
