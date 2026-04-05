"""GDPEval rubric definitions and utilities."""

import logging
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from h_arcane.benchmarks.gdpeval.rules import GDPEvalRule
from h_arcane.core._internal.db.models import CriterionResult, Evaluation, TaskEvaluationResult
from h_arcane.core._internal.evaluation.schemas import CriterionSpec, TaskEvaluationContext


class EvaluationStage(BaseModel):
    """Sequential stage in evaluation pipeline.

    Stages evaluate in order. Each stage can be:
    - A gate (must pass to continue)
    - Optional (failure doesn't stop evaluation)
    - Scored (contributes to total score)
    """

    name: str = Field(description="Stage name (e.g., 'Format Validation Gate')")

    description: str = Field(description="What this stage evaluates")

    is_required: bool = Field(
        default=True, description="Must pass this stage to proceed to next stages"
    )

    max_points: float = Field(gt=0, description="Maximum points for this stage")

    min_score_to_pass: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Minimum absolute score needed to pass this stage. "
            "⚠️ CRITICAL: Must be <= max_points! ⚠️ "
            "This is an ABSOLUTE score, not a ratio. "
            "Example: If max_points=8, min_score_to_pass can be 4, 5, 6, 7, or 8 (but NEVER 9 or higher!). "
            "For ~50% threshold: use max_points/2. For ~75% threshold: use max_points*0.75."
        ),
    )

    rules: list[GDPEvalRule] = Field(description="Rules evaluated in this stage", min_length=1)

    on_failure_action: Literal["skip_remaining", "zero_category", "continue"] = Field(
        default="skip_remaining",
        description=(
            "What to do if stage fails:\n"
            "- 'skip_remaining': Stop evaluation, return current score\n"
            "- 'zero_category': Set entire category score to 0\n"
            "- 'continue': Continue to next stage regardless"
        ),
    )

    on_failure_score: float = Field(
        default=0.0,
        description="Score if stage fails and on_failure_action='zero_category'",
    )

    @model_validator(mode="after")
    def validate_min_score(self) -> "EvaluationStage":
        """Ensure min_score_to_pass is achievable given max_points.

        Auto-corrects if min_score_to_pass > max_points by setting to 25% of max_points.
        """
        if self.min_score_to_pass > self.max_points:
            original = self.min_score_to_pass
            self.min_score_to_pass = self.max_points * 0.25
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Auto-corrected min_score_to_pass: {original:.1f} > max_points ({self.max_points:.1f}). "
                f"Set to {self.min_score_to_pass:.1f} (25% of max_points) for stage '{self.name}'"
            )
        return self


class StagedRubric(BaseModel):
    """Rubric with sequential evaluation stages.

    Evaluation proceeds through stages in order:
    1. Evaluate all rules in stage
    2. Check if stage passed (score >= threshold)
    3. If failed and required: apply failure action
    4. If passed or not required: continue to next stage

    Final score is sum of all evaluated stages (capped at max_total_score).
    """

    benchmark: Literal["gdpeval"] = "gdpeval"  # Discriminator for polymorphic deserialization

    category_name: str = Field(description="High-level category name")

    rationale: str | None = Field(
        default=None, description="Explanation of rubric design and stage structure"
    )

    max_total_score: float = Field(
        gt=0, description="Maximum possible total score across all stages"
    )

    stages: list[EvaluationStage] = Field(description="Evaluation stages in order", min_length=1)
    criteria: list[CriterionSpec] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def populate_criteria(self) -> "StagedRubric":
        """Validate stages and derive executable criterion specs."""
        total_max = sum(stage.max_points for stage in self.stages)
        if total_max > self.max_total_score:
            raise ValueError(
                f"Sum of stage max points ({total_max}) exceeds "
                f"category max ({self.max_total_score})"
            )
        self.criteria = flatten_rubric(self)
        return self

    def aggregate(
        self,
        context: TaskEvaluationContext,
        criterion_results: list[CriterionResult],
    ) -> TaskEvaluationResult:
        stage_results = _rebuild_stage_results(criterion_results, self)
        aggregate = _calculate_aggregate_scores(context.run_id, stage_results, self)

        return TaskEvaluationResult(
            run_id=context.run_id,
            criterion_results=[cr.model_dump() for cr in criterion_results],
            total_score=aggregate.total_score,
            max_score=aggregate.max_score,
            normalized_score=aggregate.normalized_score,
            stages_evaluated=aggregate.stages_evaluated,
            stages_passed=aggregate.stages_passed,
            failed_gate=aggregate.failed_gate,
        )


class GDPEvalStagedRubric(BaseModel):
    """Wrapper for GDPEval task rubric with staged evaluation."""

    task_id: str = Field(description="GDPEval task ID")
    rubric: StagedRubric = Field(description="Staged rubric")


class GDPEvalTask(BaseModel):
    """A GDPEval task with its rubric."""

    task_id: str
    task_description: str
    reference_files: list[Path]
    rubric: StagedRubric
    category: str


def flatten_rubric(
    rubric: StagedRubric,
) -> list[CriterionSpec]:
    """Flatten a staged rubric into executable criterion specs."""
    criteria = []

    for stage_idx, stage in enumerate(rubric.stages):
        for criterion_idx, rule in enumerate(stage.rules):
            criteria.append(
                CriterionSpec(
                    criterion=rule,
                    criterion_idx=criterion_idx,
                    max_score=rule.weight * stage.max_points,
                    stage_idx=stage_idx,
                    stage_name=stage.name,
                )
            )

    return criteria


def _rebuild_stage_results(
    criterion_results: list[CriterionResult],
    rubric: StagedRubric,
) -> list[dict]:
    """Rebuild criterion results into stage structure."""
    stage_results = []

    for stage_idx, stage in enumerate(rubric.stages):
        stage_criteria = [cr for cr in criterion_results if cr.stage_num == stage_idx]

        stage_score = sum(cr.score for cr in stage_criteria)
        stage_score = min(stage_score, stage.max_points)

        stage_result = {
            "stage_num": stage_idx,
            "stage_name": stage.name,
            "score": stage_score,
            "max_points": stage.max_points,
            "passed": stage_score >= stage.min_score_to_pass,
            "criteria": [
                {
                    "criterion_num": cr.criterion_num,
                    "criterion_type": cr.criterion_type,
                    "score": cr.score,
                    "max_score": cr.max_score,
                    "feedback": cr.feedback,
                    "evaluated_action_ids": cr.evaluated_action_ids,
                    "evaluated_resource_ids": cr.evaluated_resource_ids,
                }
                for cr in stage_criteria
            ],
        }
        stage_results.append(stage_result)

    return stage_results


def _calculate_aggregate_scores(
    run_id: UUID,
    stage_results: list[dict],
    rubric: StagedRubric,
) -> Evaluation:
    """Calculate aggregate scores from stage results."""
    total_score = 0.0
    max_score = rubric.max_total_score
    stages_evaluated = 0
    stages_passed = 0
    failed_gate = None

    for stage_result in stage_results:
        stages_evaluated += 1
        total_score += stage_result["score"]

        if stage_result["passed"]:
            stages_passed += 1
        else:
            # Check if this stage was required (gate)
            stage_idx: int = stage_result["stage_num"]
            stage: EvaluationStage = rubric.stages[stage_idx]
            if stage.is_required and failed_gate is None:
                failed_gate = stage.name

            # Apply failure action
            if stage.on_failure_action == "skip_remaining":
                break
            elif stage.on_failure_action == "zero_category":
                total_score -= stage_result["score"]  # Remove what we added
                total_score += stage.on_failure_score

    # Normalize score
    normalized_score = total_score / max_score if max_score > 0 else 0.0
    normalized_score = min(max(normalized_score, 0.0), 1.0)

    return Evaluation(
        run_id=run_id,
        total_score=total_score,
        max_score=max_score,
        normalized_score=normalized_score,
        stages_evaluated=stages_evaluated,
        stages_passed=stages_passed,
        failed_gate=failed_gate,
    )
