"""Application settings loaded from environment / .env file."""

import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql://ergon:ergon_dev@localhost:5433/ergon",
        validation_alias=AliasChoices("ERGON_DATABASE_URL", "DATABASE_URL"),
    )

    openai_api_key: str = ""  # slopcop: ignore[no-str-empty-default]
    openrouter_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY"),
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("OPENROUTER_BASE_URL"),
    )

    e2b_api_key: str = ""  # slopcop: ignore[no-str-empty-default]
    exa_api_key: str = ""  # slopcop: ignore[no-str-empty-default]

    inngest_event_key: str = "dev"
    inngest_dev: bool = True
    inngest_api_base_url: str = "http://localhost:8289"

    default_tokenizer: str = "HuggingFaceTB/SmolLM2-135M-Instruct"

    otel_traces_enabled: bool = False
    otel_service_name: str = "ergon-core"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_exporter_otlp_insecure: bool = True
    otel_max_attribute_length: int = 4000
    otel_stdout_stderr_max_length: int = 4000
    otel_tool_payload_max_length: int = 4000

    # Set by eval watcher / checkpoint subprocess (see `eval_runner.py`); optional in `.env`.
    checkpoint_step: int | None = Field(
        default=None,
        validation_alias=AliasChoices("ERGON_CHECKPOINT_STEP"),
    )
    checkpoint_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ERGON_CHECKPOINT_PATH"),
    )
    hf_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("HF_API_KEY"),
    )

    @property
    def data_dir(self) -> Path:
        return Path(__file__).parent.parent / "data"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    def missing_values(self, names: list[str]) -> list[str]:
        return [
            name
            for name in names
            if not getattr(self, name, "")  # slopcop: ignore[no-hasattr-getattr]
        ]

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

if settings.openrouter_api_key:
    os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)
