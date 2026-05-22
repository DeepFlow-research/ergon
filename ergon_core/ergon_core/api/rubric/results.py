"""Public rubric result models."""

from typing import Any

from ergon_core.api.criterion.outcome import CriterionOutcome
from pydantic import BaseModel, Field


class TaskEvaluationResult(BaseModel):
    """Aggregated evaluation result for one task across all criteria."""

    model_config = {"frozen": True}

    task_slug: str
    score: float
    passed: bool
    evaluator_name: str
    criterion_results: list[CriterionOutcome] = Field(default_factory=list)
    feedback: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
