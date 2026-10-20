"""Settings come from environment variables or a local .env file (never committed)."""

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Any OpenAI-compatible provider works; Nebius Token Factory is the default.
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    nebius_api_key: SecretStr

    # Big model for root-cause reasoning, small one for fast everyday calls.
    model_smart: str = "nvidia/nemotron-3-super-120b-a12b"
    model_fast: str = "nvidia/nemotron-3-super-120b-a12b"

    # 1024 dims keeps vectors under pgvector's 2000-dim HNSW index limit.
    embedding_model: str = "Qwen/Qwen3-Embedding-8B"
    embedding_dim: int = 1024

    database_url: str = "postgresql://workbench:workbench@localhost:5432/workbench"
    # "pgvector" uses database_url; "memory" embeds runbooks/ at first use (no database needed).
    kb_backend: Literal["pgvector", "memory"] = "pgvector"

    # Token usage log for the Usage page (counts only, no prompt text) and optional prices
    # in USD per 1M tokens, e.g. PRICES='{"nvidia/nemotron-3-super-120b-a12b": [0.1, 0.5]}'.
    usage_file: str = "var/usage.jsonl"
    prices: dict[str, list[float]] = {}

    # Server. The container sets HOST=0.0.0.0; locally it stays on loopback.
    host: str = "127.0.0.1"
    port: int = 8000

    # Public demo guards. Leave demo_password empty to turn the password off (local use).
    demo_password: SecretStr | None = None
    daily_run_limit: int = 200
    max_log_bytes: int = 20_000
    # Models the API accepts; anything else is refused so callers cannot pick a pricier one.
    allowed_models: list[str] = [
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/Nemotron-3-Ultra-550b-a55b",
    ]


settings = Settings()
