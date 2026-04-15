"""Public runtime-facing evaluation context."""

from typing import Any
from uuid import UUID

from ergon_core.api.results import WorkerOutput
from ergon_core.api.task_types import BenchmarkTask
from pydantic import BaseModel, ConfigDict, Field


class EvaluationContext(BaseModel):
    """Thin evaluation context: sandbox access + task identity.

    Thin by design. Criteria own their data-pulling -- they connect to the
    sandbox via sandbox_id and pull what they need. The old pattern
    pre-collected resources, which broke agentic evaluators that need to
    explore freely.

    ``runtime`` is injected by ``InngestCriterionExecutor`` before calling
    ``Criterion.evaluate(context)``.  Criteria that need LLM-judge
    capabilities read ``context.runtime.call_llm_judge(...)``.  Criteria
    that don't need a runtime simply ignore the field.

    The runtime field is typed as ``Any`` to avoid a circular import between
    ``ergon_core.api`` and ``ergon_core.core.runtime.evaluation``.  At
    runtime it will be a ``CriterionRuntime`` (protocol) or ``None``.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    run_id: UUID
    task: BenchmarkTask
    worker_result: WorkerOutput
    sandbox_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
    runtime: Any = None  # slopcop: ignore[no-typing-any]  CriterionRuntime | None
