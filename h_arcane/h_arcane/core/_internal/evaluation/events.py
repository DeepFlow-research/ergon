"""Inngest event schemas for evaluation domain."""

from typing import ClassVar
from uuid import UUID

from h_arcane.benchmarks.types import AnyRubric
from h_arcane.core._internal.db.models import ResourceRecord
from h_arcane.core._internal.evaluation.criterion_types import AnyCriterion
from h_arcane.core._internal.events.base import InngestEventContract


class TaskEvaluationEvent(InngestEventContract):
    """Event for task/evaluate.

    Triggers: evaluate_task_run Inngest function.
    """

    name: ClassVar[str] = "task/evaluate"

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    evaluator_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[ResourceRecord]
    rubric: AnyRubric

    model_config = {"extra": "allow"}  # Allow extra fields for rubric polymorphism


class CriterionEvaluationEvent(InngestEventContract):
    """Event for criterion/evaluate.

    Triggers: evaluate_criterion_fn Inngest function.
    """

    name: ClassVar[str] = "criterion/evaluate"

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    evaluator_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[ResourceRecord]

    # Benchmark identification (for sandbox manager lookup)
    benchmark_name: str

    # Stage info as primitives (instead of EvaluationStage object)
    stage_name: str
    stage_idx: int
    criterion_idx: int
    max_score: float

    # Criterion as discriminated union - Pydantic handles serialization/deserialization
    criterion: AnyCriterion

    model_config = {"extra": "allow"}  # Allow extra fields for criterion polymorphism
