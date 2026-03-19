"""Smoke test rubric for evaluation pipeline testing."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from h_arcane.core._internal.db.models import CriterionResult, TaskEvaluationResult
from h_arcane.core._internal.evaluation.rules import CodeRule, LLMJudgeRule
from h_arcane.core._internal.evaluation.schemas import CriterionSpec, TaskEvaluationContext

SmokeTestCriterion = CodeRule | LLMJudgeRule


class SmokeTestRubric(BaseModel):
    """Simple rubric for smoke test evaluation.

    Supports both CodeRule and LLMJudgeRule to test the full evaluation
    pipeline including sandbox code execution.
    """

    benchmark: Literal["smoke_test"] = "smoke_test"
    rules: list[SmokeTestCriterion] = Field(
        description="List of evaluation criteria (CodeRule or LLMJudgeRule)"
    )
    criteria: list[CriterionSpec] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def populate_criteria(self) -> "SmokeTestRubric":
        self.criteria = [
            CriterionSpec(
                criterion=criterion,
                criterion_idx=idx,
                max_score=criterion.weight,
                stage_idx=0,
                stage_name=f"Rule-{idx}",
            )
            for idx, criterion in enumerate(self.rules)
        ]
        return self

    def aggregate(
        self,
        context: TaskEvaluationContext,
        criterion_results: list[CriterionResult],
    ) -> TaskEvaluationResult:
        total_score = sum(result.score for result in criterion_results)
        max_score = sum(result.max_score for result in criterion_results)
        normalized_score = total_score / max_score if max_score > 0 else 0.0

        return TaskEvaluationResult(
            run_id=context.run_id,
            criterion_results=[cr.model_dump() for cr in criterion_results],
            total_score=total_score,
            max_score=max_score,
            normalized_score=normalized_score,
            stages_evaluated=1,
            stages_passed=1 if total_score > 0 else 0,
            failed_gate=None,
        )
