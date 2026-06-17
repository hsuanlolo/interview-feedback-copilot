"""Application configuration loaded from environment variables."""

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
    cors_origins: list[str] = ["http://localhost:3000"]

    # Extraction
    max_debrief_size_chars: int = 50_000  # ~10k words, well above realistic debrief length
    baseline_mode: bool = False  # Force baseline extractor even if API key present


settings = Settings()
