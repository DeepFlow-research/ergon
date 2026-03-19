"""MiniF2F rubric definition."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from h_arcane.core._internal.db.models import CriterionResult, TaskEvaluationResult
from h_arcane.core._internal.evaluation.schemas import CriterionSpec, TaskEvaluationContext
from h_arcane.benchmarks.minif2f.rules import ProofVerificationRule


class MiniF2FRubric(BaseModel):
    """MiniF2F rubric for proof verification."""

    benchmark: Literal["minif2f"] = "minif2f"

    criteria: list[CriterionSpec] = Field(default_factory=list, exclude=True)
    max_score: float = Field(default=1.0, description="Maximum score for proof verification")
    partial_credit_for_syntax: float = Field(
        default=0.2,
        description="Partial credit multiplier for valid Lean syntax that doesn't prove theorem",
    )

    @model_validator(mode="after")
    def populate_criteria(self) -> "MiniF2FRubric":
        self.criteria = [
            CriterionSpec(
                criterion=ProofVerificationRule(
                    name="proof_verification",
                    description="Verify Lean proof compiles and proves the theorem",
                    weight=1.0,
                ),
                criterion_idx=0,
                max_score=self.max_score,
                stage_idx=0,
                stage_name="Proof Verification",
            )
        ]
        return self

    def aggregate(
        self,
        context: TaskEvaluationContext,
        criterion_results: list[CriterionResult],
    ) -> TaskEvaluationResult:
        """Aggregate MiniF2F proof verification results."""
        if len(criterion_results) != 1:
            raise ValueError(
                f"MiniF2FRubric expects exactly 1 criterion result, got {len(criterion_results)}"
            )

        criterion_result = criterion_results[0]

        if criterion_result.score >= self.max_score:
            total_score = self.max_score
            passed = True
        elif criterion_result.score > 0:
            total_score = self.partial_credit_for_syntax * self.max_score
            passed = False
        else:
            total_score = 0.0
            passed = False

        normalized_score = total_score / self.max_score if self.max_score > 0 else 0.0

        return TaskEvaluationResult(
            run_id=context.run_id,
            criterion_results=[criterion_result.model_dump()],
            total_score=total_score,
            max_score=self.max_score,
            normalized_score=normalized_score,
            stages_evaluated=1,
            stages_passed=1 if passed else 0,
            failed_gate="Proof Verification" if not passed else None,
        )
