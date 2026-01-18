"""Inngest event schemas for evaluation domain.

These are the contracts for evaluation-related Inngest events.
"""

from typing import ClassVar

from pydantic import BaseModel

from h_arcane.benchmarks.types import AnyRubric, AnyRule
from h_arcane.core._internal.db.models import Resource
from h_arcane.core._internal.events.base import InngestEventContract


class TaskEvaluationEvent(InngestEventContract):
    """Event for task/evaluate.

    Triggers: evaluate_task_run Inngest function.
    """

    name: ClassVar[str] = "task/evaluate"

    run_id: str
    task_input: str
    agent_reasoning: str
    agent_outputs: list[Resource]
    rubric: AnyRubric

    model_config = {"extra": "allow"}  # Allow extra fields for rubric polymorphism


class CriterionEvaluationEvent(InngestEventContract):
    """Event for criterion/evaluate.

    Triggers: evaluate_criterion_fn Inngest function.
    """

    name: ClassVar[str] = "criterion/evaluate"

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

    model_config = {"extra": "allow"}  # Allow extra fields for rule polymorphism


class RunEvaluateResult(BaseModel):
    """Result from run_evaluate function (not an event contract)."""

    run_id: str
    normalized_score: float
    questions_asked: int
