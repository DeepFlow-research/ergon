"""Public runtime-facing evaluation context."""

from typing import Any
from uuid import UUID

from ergon_core.api.results import WorkerResult
from ergon_core.api.task_types import BenchmarkTask
from pydantic import BaseModel, Field


class EvaluationContext(BaseModel):
    """Thin evaluation context: sandbox access + task identity.

    Thin by design. Criteria own their data-pulling -- they connect to the
    sandbox via sandbox_id and pull what they need. The old pattern
    pre-collected resources, which broke agentic evaluators that need to
    explore freely.
    """

    model_config = {"frozen": True}

    run_id: UUID
    task: BenchmarkTask
    worker_result: WorkerResult
    sandbox_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
