"""Public result types returned by workers, criteria, and evaluators."""

from typing import Any

from pydantic import BaseModel, Field

from ergon_core.api.generation import GenerationTurn


class WorkerResult(BaseModel):
    """Result of a single Worker.execute() invocation."""

    model_config = {"frozen": True}

    output: str
    success: bool = True
    turns: list[GenerationTurn] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]


class CriterionResult(BaseModel):
    """Result of a single Criterion.evaluate() invocation."""

    model_config = {"frozen": True}

    name: str
    score: float
    passed: bool
    weight: float = 1.0
    feedback: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]


class TaskEvaluationResult(BaseModel):
    """Aggregated evaluation result for one task across all criteria."""

    model_config = {"frozen": True}

    task_key: str
    score: float
    passed: bool
    evaluator_name: str
    criterion_results: list[CriterionResult] = Field(default_factory=list)
    feedback: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
