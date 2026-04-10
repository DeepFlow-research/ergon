"""Evaluation lifecycle event contracts."""

from typing import ClassVar
from uuid import UUID

from h_arcane.core.runtime.events.base import InngestEventContract


class TaskEvaluationEvent(InngestEventContract):
    """Request to evaluate a task. Triggers evaluate_task_run."""

    name: ClassVar[str] = "task/evaluate"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    evaluator_id: UUID
    evaluator_binding_key: str


class CriterionEvaluationEvent(InngestEventContract):
    """Request to evaluate a single criterion. Triggers evaluate_criterion."""

    name: ClassVar[str] = "criterion/evaluate"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    evaluator_id: UUID
    criterion_idx: int
