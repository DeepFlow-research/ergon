from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Database
    database_url: str = "postgresql://h_arcane:h_arcane_dev@localhost:5433/h_arcane"

    # Test Database (separate from production for E2E tests)
    database_url_test: str = "postgresql://h_arcane:h_arcane_dev@localhost:5433/h_arcane_test"

    # OpenAI
    openai_api_key: str = ""

    # E2B Sandbox
    e2b_api_key: str = ""

    # Exa API (for ResearchRubrics web search)
    exa_api_key: str = ""

    # Inngest
    inngest_event_key: str = "dev"
    inngest_dev: bool = True
    inngest_api_base_url: str = "http://localhost:8289"  # Default for local dev (host port)

    # Data directory (computed from project root)
    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        return Path(__file__).parent.parent / "data"

    # Output directory for runs
    @property
    def runs_dir(self) -> Path:
        """Get the runs directory path."""
        return self.data_dir / "runs"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = Settings()

for key, value in settings.model_dump().items():
    if key in ["openai_api_key"]:
        if value == "":
            raise ValueError(
                f"Environment variable {key} is not set. Please set it in your .env file or environment variables."
            )
