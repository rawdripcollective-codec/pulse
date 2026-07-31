"""Pulse configuration via environment variables.

All settings are loaded from `.env` (if present) and the process environment.
Override anything in production by setting the matching env var.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── Application ─────────────────────────────────────────
    app_name: str = "Pulse"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"

    # ─── Database ────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://pulse:pulse@localhost:5432/pulse"
    database_url_sync: str = "postgresql://pulse:pulse@localhost:5432/pulse"

    # ─── Redis (WebSocket pub/sub + agent state) ─────────────
    redis_url: str = "redis://localhost:6379/0"

    # ─── GitHub ──────────────────────────────────────────────
    github_app_id: str = ""
    github_app_private_key: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    github_webhook_secret: str = ""

    # ─── LLM ─────────────────────────────────────────────────
    llm_provider: str = "anthropic"  # anthropic, openai, ollama
    llm_model: str = "claude-sonnet-4-20250514"
    llm_api_key: str = ""
    llm_base_url: str = ""  # For Ollama: http://localhost:11434/v1

    # ─── Embeddings ──────────────────────────────────────────
    embedding_model: str = "voyage-code-2"
    embedding_api_key: str = ""
    embedding_dimensions: int = 1536

    # ─── LanceDB storage ─────────────────────────────────────
    lancedb_path: str = str(Path.home() / ".pulse" / "lancedb")

    # ─── Indexing limits ─────────────────────────────────────
    max_repo_size_bytes: int = 500 * 1024 * 1024  # 500 MB
    max_file_size_bytes: int = 2 * 1024 * 1024  # 2 MB per file

    # ─── Paths ───────────────────────────────────────────────
    data_dir: str = str(Path.home() / ".pulse")


settings = Settings()
