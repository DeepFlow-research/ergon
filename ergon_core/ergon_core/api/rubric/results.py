"""Public rubric result models."""

from ergon_core.api.criterion.results import CriterionOutcome
from ergon_core.core.shared.json_types import JsonObject
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
    metadata: JsonObject = Field(default_factory=dict)
