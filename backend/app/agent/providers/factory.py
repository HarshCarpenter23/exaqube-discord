"""Selects the LLM provider from configuration.

Adding a provider means writing one new file that implements LLMProvider and
adding a branch here — the agent loop is untouched.
"""

from __future__ import annotations

from app.agent.providers.base import LLMProvider
from app.config import Settings


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "groq":
        from app.agent.providers.groq_provider import GroqProvider

        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.llm_model,
            max_completion_tokens=settings.llm_max_completion_tokens,
        )
    raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
