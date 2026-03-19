"""ResearchRubrics rubric definition."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

from h_arcane.benchmarks.researchrubrics.schemas import RubricCriterion
from h_arcane.core._internal.db.models import CriterionResult, TaskEvaluationResult
from h_arcane.core._internal.evaluation.rules import LLMJudgeRule
from h_arcane.core._internal.evaluation.schemas import CriterionSpec, TaskEvaluationContext


class ResearchRubricsRubric(BaseModel):
    """ResearchRubrics rubric for weighted criteria evaluation.

    Unlike GDPEval's staged rubric, ResearchRubrics has a flat list of
    weighted criteria without stages. Weights can be positive or negative.
    """

    benchmark: Literal["researchrubrics"] = "researchrubrics"
    rubric_criteria: list[RubricCriterion] = Field(
        description="Raw dataset criteria used to construct executable criterion specs",
        validation_alias=AliasChoices("rubric_criteria", "criteria"),
    )
    criteria: list[CriterionSpec] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def populate_criteria(self) -> "ResearchRubricsRubric":
        self.criteria = [
            CriterionSpec(
                criterion=LLMJudgeRule(
                    name=f"criterion_{idx}",
                    description=criterion.criterion,
                    weight=1.0,
                    judge_prompt=self._build_judge_prompt(criterion),
                    expectation=None,
                    axis=criterion.axis,
                ),
                criterion_idx=idx,
                max_score=abs(criterion.weight),
                stage_idx=0,
                stage_name=f"Criterion-{idx}",
                aggregation_weight=criterion.weight,
            )
            for idx, criterion in enumerate(self.rubric_criteria)
        ]
        return self

    def aggregate(
        self,
        context: TaskEvaluationContext,
        criterion_results: list[CriterionResult],
    ) -> TaskEvaluationResult:
        total_score = 0.0
        max_possible_score = 0.0
        min_possible_score = 0.0

        for spec, result in zip(self.criteria, criterion_results, strict=True):
            if result.max_score != 0 and result.score > 0:
                weighted_score = spec.aggregation_weight
            else:
                weighted_score = 0.0

            total_score += weighted_score

            if spec.aggregation_weight > 0:
                max_possible_score += spec.aggregation_weight
            else:
                min_possible_score += spec.aggregation_weight

        score_range = max_possible_score - min_possible_score
        normalized_score = (
            (total_score - min_possible_score) / score_range if score_range > 0 else 0.0
        )

        return TaskEvaluationResult(
            run_id=context.run_id,
            criterion_results=[cr.model_dump() for cr in criterion_results],
            total_score=total_score,
            max_score=max_possible_score,
            normalized_score=normalized_score,
            stages_evaluated=1,
            stages_passed=1 if total_score > 0 else 0,
            failed_gate=None,
        )

    def _build_judge_prompt(self, criterion: RubricCriterion) -> str:
        """
        Build judge prompt for evaluating a single criterion.

        Args:
            criterion: The RubricCriterion to build a prompt for

        Returns:
            System prompt for the LLM judge
        """
        axis_context = (
            f"\n\nThis criterion belongs to the '{criterion.axis}' axis." if criterion.axis else ""
        )
        weight_note = f"\n\nWeight: {criterion.weight}" if criterion.weight != 1.0 else ""

        return f"""You are an expert evaluator assessing research reports against specific criteria.

Your task is to evaluate whether a research report meets this criterion:
{criterion.criterion}{axis_context}{weight_note}

You will be given:
- The original task/request given to the researcher
- The researcher's reasoning and thought process
- The final research report/output

Evaluate whether the output meets this criterion. Provide:
1. Detailed reasoning explaining your decision, citing specific evidence from the task input, researcher reasoning, and outputs
2. A binary verdict: True if the criterion is met, False otherwise

This is a pass/fail decision. The criterion is either satisfied (True) or not satisfied (False).
Be thorough but fair in your evaluation."""
