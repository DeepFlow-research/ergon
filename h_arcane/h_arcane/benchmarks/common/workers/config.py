"""Worker configuration types."""

from enum import Enum

from pydantic import BaseModel

from h_arcane.benchmarks.enums import BenchmarkName


class BaselineType(str, Enum):
    """Available baseline worker types."""

    REACT = "react"  # ReActWorker - asks questions organically


class WorkerConfig(BaseModel):
    """Configuration for running a worker on a benchmark."""

    benchmark_name: BenchmarkName
    system_prompt: str
    max_questions: int = 10
