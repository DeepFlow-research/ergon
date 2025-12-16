"""Shared benchmark types and configuration."""

from enum import Enum
from pydantic import BaseModel


class BenchmarkName(str, Enum):
    """Supported benchmark names."""

    GDPEVAL = "gdpeval"
    MINIF2F = "minif2f"
    RESEARCHRUBRICS = "researchrubrics"


class WorkerConfig(BaseModel):
    """Configuration for running a worker on a benchmark."""

    benchmark_name: BenchmarkName
    system_prompt: str
    max_questions: int = 10
