from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Database
    database_url: str = "postgresql://h_arcane:h_arcane_dev@localhost:5433/h_arcane"

    # OpenAI
    openai_api_key: str = ""

    # E2B Sandbox
    e2b_api_key: str = ""

    # Inngest
    inngest_event_key: str = "dev"
    inngest_dev: bool = True
    inngest_api_base_url: str = "http://localhost:8289"  # Default for local dev (host port)

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = Settings()
