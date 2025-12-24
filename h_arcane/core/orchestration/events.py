"""Inngest event schemas for H-ARCANE experiments."""

from pydantic import BaseModel

from h_arcane.core.db.models import Resource
from h_arcane.benchmarks.types import AnyRubric, AnyRule


class ExecutionDoneEvent(BaseModel):
    """Event data for execution/done event."""

    run_id: str


class RunCleanupEvent(BaseModel):
    """Event data for run/cleanup event."""

    run_id: str
    status: str  # "completed" or "failed"
    error_message: str | None = None


class TaskEvaluationEvent(BaseModel):
    """Event data for task/evaluate event.

    Pydantic handles serialization/deserialization automatically:
    - agent_outputs: list[Resource] serializes to JSON, deserializes back
    - rubric: AnyRubric uses discriminator to pick correct type
    """

    run_id: str
    task_input: str
    agent_reasoning: str
    agent_outputs: list[Resource]
    rubric: AnyRubric


class RunEvaluateResult(BaseModel):
    """Result from run_evaluate function."""

    run_id: str
    normalized_score: float
    questions_asked: int


class CriterionEvaluationEvent(BaseModel):
    """Event data for criterion/evaluate event.

    Pydantic handles serialization/deserialization automatically:
    - agent_outputs: list[Resource] serializes to JSON, deserializes back
    - rule: AnyRule uses discriminator to pick correct type
    """

    run_id: str
    task_input: str
    agent_reasoning: str
    agent_outputs: list[Resource]

    # Stage info as primitives (instead of EvaluationStage object)
    stage_name: str
    stage_idx: int
    rule_idx: int
    max_score: float

    # Rule as discriminated union - Pydantic handles serialization/deserialization
    rule: AnyRule
