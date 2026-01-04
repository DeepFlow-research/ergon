"""Experiment configuration."""

from pydantic import BaseModel, Field


class ExperimentConfig(BaseModel):
    """Configuration for experiment runs."""

    # Baseline selection (e.g. "react")
    baseline: str = Field(default="react")

    # Worker configuration
    worker_model: str = Field(default="gpt-4o")
    max_questions: int = Field(default=10, description="Safety limit per run")

    # Retry policy
    max_retries: int = Field(default=2)

    # Note: Concurrency is handled at Inngest function level, not in config


DEFAULT_CONFIG = ExperimentConfig()
