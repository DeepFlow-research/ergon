"""Evaluation result models."""

from pydantic import BaseModel

from h_arcane.schemas.staged_rubric_schema import (
    CodeRule,
    EvaluationStage,
    LLMJudgeRule,
)


class FlattenedCriterion(BaseModel):
    """A flattened criterion with stage, rule, and indices for step serialization."""

    stage: EvaluationStage
    rule: CodeRule | LLMJudgeRule
    stage_idx: int
    rule_idx: int
