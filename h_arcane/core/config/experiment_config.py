"""Experiment configuration."""

from pydantic import BaseModel, Field

from h_arcane.benchmarks.common.workers.config import BaselineType


class ExperimentConfig(BaseModel):
    """Configuration for experiment runs."""

    # Baseline selection
    baseline: BaselineType = Field(default=BaselineType.REACT)

    # Worker configuration
    worker_model: str = Field(default="gpt-4o")
    max_questions: int = Field(default=10, description="Safety limit per run")

    # Retry policy
    max_retries: int = Field(default=2)

    # Note: Concurrency is handled at Inngest function level, not in config


DEFAULT_CONFIG = ExperimentConfig()
