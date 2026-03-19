from pathlib import Path
from typing import Literal
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

    # OTEL tracing
    otel_traces_enabled: bool = False
    otel_service_name: str = "h-arcane"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_exporter_otlp_insecure: bool = True
    otel_max_attribute_length: int = 4000
    otel_stdout_stderr_max_length: int = 4000
    otel_tool_payload_max_length: int = 4000

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

    def get_database_url(self, target: Literal["main", "test"] = "main") -> str:
        """Resolve the database URL for the requested target."""
        if target == "test":
            return self.database_url_test
        return self.database_url

    def missing_values(self, names: list[str]) -> list[str]:
        """Return env-backed setting names that are currently blank."""
        return [name for name in names if not getattr(self, name, "")]

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = Settings()
