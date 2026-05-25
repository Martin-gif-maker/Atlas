"""Atlas — centralised application settings.

All configuration is loaded from environment variables and the .env file.
Import the shared ``settings`` singleton anywhere you need a config value:

    from config import settings
    key = settings.openai_api_key
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for Atlas.

    Values are read from environment variables (case-insensitive) and from
    a ``.env`` file in the project root, with environment variables taking
    priority.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # silently ignore unknown env vars
    )

    # ------------------------------------------------------------------
    # Required secrets — the app will not start without these.
    # ------------------------------------------------------------------
    openai_api_key: str = Field(..., description="OpenAI API key (used for Whisper STT).")
    groq_api_key: str = Field(..., description="Groq API key (used for the LLM).")

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    session_secret: str = Field(
        default="dev-secret-change-me",
        description=(
            "Secret key for signing session cookies. "
            "Generate a strong value with: python -c \"import secrets; print(secrets.token_hex(32))\""
        ),
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    atlas_db_path: Path = Field(
        default=Path(__file__).parent / "atlas.db",
        description="Filesystem path to the SQLite database file.",
    )

    # ------------------------------------------------------------------
    # Local dev server (used only when running main.py directly)
    # ------------------------------------------------------------------
    host: str = Field(default="127.0.0.1", description="Bind address for the dev server.")
    port: int = Field(default=8000, description="Port for the dev server.")
    reload: bool = Field(default=True, description="Enable auto-reload in development.")


# Single shared instance — import this rather than constructing a new Settings().
settings = Settings()
