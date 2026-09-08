"""Application configuration.

One Settings object, loaded from environment variables (and a local .env in
development). Required values have no default, so a missing one makes the app
fail loudly at startup instead of 500-ing later at request time.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str                 # app role (read/write on app tables)
    readonly_database_url: str        # agent role (read-only, enforced at DB)
    agent_ro_password: str = "agent_ro_pw"   # used by migrate to create the RO role

    # LLM provider (default: Groq). The provider is selected by llm_provider and
    # sits behind an interface, so another provider is a new file + these vars.
    llm_provider: str = "groq"
    llm_model: str = "openai/gpt-oss-120b"
    groq_api_key: str = ""            # required when llm_provider == "groq"
    llm_max_completion_tokens: int = 1024   # keep responses bounded (free-tier TPM)
    result_preview_rows: int = 15     # rows of a query result shown to the model

    # Agent behaviour
    agent_max_steps: int = 6
    agent_max_retries: int = 2

    # Safety limits
    row_cap: int = 5000
    statement_timeout_ms: int = 5000
    artifact_dir: str = "/artifacts"
    artifact_max_rows: int = 50_000
    artifact_max_bytes: int = 10 * 1024 * 1024
    pptx_max_slides: int = 20

    # Data load
    data_dir: str = "/data/dataset"   # where the dataset CSVs are mounted

    # Misc
    log_level: str = "info"

    def require_provider_key(self) -> None:
        """Called at startup: the chosen provider must actually be usable."""
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=groq but GROQ_API_KEY is not set. "
                "Set it in your .env before starting the backend."
            )


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the environment is read once per process."""
    return Settings()
