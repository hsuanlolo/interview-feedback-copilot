"""Application configuration loaded from environment variables."""

from __future__ import annotations

from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-4-8"
    llm_mock_mode: bool = False  # Set True in tests to avoid real API calls

    # Database
    database_url: str = "sqlite+aiosqlite:///./interview_copilot.db"

    # App
    app_title: str = "Interview Feedback Copilot"
    app_version: str = "0.1.0"
    # Comma-separated in env: CORS_ORIGINS=https://myapp.vercel.app,http://localhost:3000
    cors_origins: List[str] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Extraction
    max_debrief_size_chars: int = 50_000  # ~10k words, well above realistic debrief length
    baseline_mode: bool = False  # Force baseline extractor even if API key present


settings = Settings()
