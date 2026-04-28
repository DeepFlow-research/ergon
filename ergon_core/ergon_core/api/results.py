"""Public result types returned by workers, criteria, and evaluators."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ergon_core.core.json_types import JsonObject


class WorkerOutput(BaseModel):
    """Final output of a worker execution.

    The worker's ``execute()`` async generator yields ``GenerationTurn``
    objects (persisted individually to PG). After the generator exhausts,
    ``Worker.get_output()`` returns this model with the execution summary.
    """

    model_config = {"frozen": True}

    output: str
    success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]


class CriterionScoreSpec(BaseModel):
    """Criterion-local score range.

    This is the range an atomic criterion can emit. Aggregation penalties and
    signed weights are evaluator/rubric concerns, not negative local scores.
    """

    model_config = {"frozen": True}

    min_score: float = 0.0
    max_score: float = 1.0


class CriterionObservationMessage(BaseModel):
    """One prompt-like message used while producing a criterion result."""

    model_config = {"frozen": True}

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class CriterionObservation(BaseModel):
    """Structured observation space for a criterion run."""

    model_config = {"frozen": True}

    prompt_messages: list[CriterionObservationMessage] = Field(default_factory=list)
    evidence_resource_ids: list[str] = Field(default_factory=list)
    evidence_action_ids: list[str] = Field(default_factory=list)
    output: JsonObject | None = None
    model: str | None = None
    details: JsonObject = Field(default_factory=dict)


class CriterionResult(BaseModel):
    """Result of a single Criterion.evaluate() invocation."""

    model_config = {"frozen": True}

    slug: str
    name: str
    score: float
    passed: bool
    weight: float = 1.0
    max_score: float = 1.0
    feedback: str | None = None
    model_reasoning: str | None = None
    skipped_reason: str | None = None
    evaluation_input: str | None = None
    evaluated_action_ids: list[str] = Field(default_factory=list)
    evaluated_resource_ids: list[str] = Field(default_factory=list)
    observation: CriterionObservation | None = None
    error: dict[str, Any] | None = None  # slopcop: ignore[no-typing-any]
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    @model_validator(mode="before")
    @classmethod
    def _populate_slug_name(cls, data):
        if isinstance(data, dict):
            if "slug" not in data and "name" in data:
                data["slug"] = data["name"]
            if "name" not in data and "slug" in data:
                data["name"] = data["slug"]
        return data


class TaskEvaluationResult(BaseModel):
    """Aggregated evaluation result for one task across all criteria."""

    model_config = {"frozen": True}

    task_slug: str
    score: float
    passed: bool
    evaluator_name: str
    criterion_results: list[CriterionResult] = Field(default_factory=list)
    feedback: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
