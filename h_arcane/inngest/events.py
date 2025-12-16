"""Inngest event schemas for H-ARCANE experiments."""

from pydantic import BaseModel

from h_arcane.db.models import Resource
from h_arcane.evaluation.rubric import EvaluationStage
from h_arcane.evaluation.rules import CodeRule, LLMJudgeRule


class ExecutionDoneEvent(BaseModel):
    """Event data for execution/done event."""

    run_id: str


class RunCleanupEvent(BaseModel):
    """Event data for run/cleanup event."""

    run_id: str
    status: str  # "completed" or "failed"
    error_message: str | None = None


class TaskEvaluationEvent(BaseModel):
    """Event data for task/evaluate event."""

    run_id: str
    task_input: str
    agent_reasoning: str
    agent_outputs: list[dict]  # Serialized Resource objects
    rubric: dict  # Serialized StagedRubric


class RunEvaluateResult(BaseModel):
    """Result from run_evaluate function."""

    run_id: str
    normalized_score: float
    questions_asked: int


class CriterionEvaluationEvent(BaseModel):
    """Event data for criterion/evaluate event."""

    run_id: str
    task_input: str
    agent_reasoning: str
    agent_outputs: list[Resource]
    stage: EvaluationStage
    rule: CodeRule | LLMJudgeRule
    stage_idx: int
    rule_idx: int
