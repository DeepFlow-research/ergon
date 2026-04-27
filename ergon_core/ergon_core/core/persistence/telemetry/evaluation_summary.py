"""Strongly-typed model for RunTaskEvaluation.summary_json.

This is the canonical schema for evaluation summary persistence.
Both the write side (evaluate_task_run.py) and read side (runs.py)
use this model — no untyped dict access.
"""

from typing import Literal

from pydantic import BaseModel, Field

EvalCriterionStatus = Literal["passed", "failed", "errored", "skipped"]


class CriterionResultEntry(BaseModel):
    """One criterion result as stored in the evaluation summary."""

    criterion_name: str
    criterion_type: str
    stage_num: int = 0
    stage_name: str = "default"
    criterion_num: int = 0
    status: EvalCriterionStatus
    score: float
    max_score: float = 1.0
    passed: bool
    weight: float = 1.0
    contribution: float
    criterion_description: str
    feedback: str | None = None
    model_reasoning: str | None = None
    skipped_reason: str | None = None
    evaluation_input: str | None = None
    evaluated_action_ids: list[str] = Field(default_factory=list)
    evaluated_resource_ids: list[str] = Field(default_factory=list)
    error: dict | None = None


class EvaluationSummary(BaseModel):
    """Typed schema for RunTaskEvaluation.summary_json."""

    evaluator_name: str
    max_score: float = 1.0
    normalized_score: float = 0.0
    stages_evaluated: int = 0
    stages_passed: int = 0
    failed_gate: str | None = None
    criterion_results: list[CriterionResultEntry] = Field(default_factory=list)
