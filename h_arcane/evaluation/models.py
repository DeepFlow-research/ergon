"""Evaluation result models."""

from pydantic import BaseModel

from h_arcane.evaluation.rubric import EvaluationStage
from h_arcane.evaluation.rules import CodeRule, LLMJudgeRule


class FlattenedCriterion(BaseModel):
    """A flattened criterion with stage, rule, and indices for step serialization."""

    stage: EvaluationStage
    rule: CodeRule | LLMJudgeRule
    stage_idx: int
    rule_idx: int
