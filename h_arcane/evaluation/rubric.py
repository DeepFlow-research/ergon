"""Rubric and stage definitions for evaluation.

Extends MA-Gym rubrics with:
- Sequential evaluation stages
- Gates (mandatory prerequisites)
- Thresholds (minimum scores to proceed)
- Conditional evaluation (skip stages if gates fail)
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from h_arcane.evaluation.rules import CodeRule, LLMJudgeRule


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

    rules: list[CodeRule | LLMJudgeRule] = Field(
        description="Rules evaluated in this stage", min_length=1
    )

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

    category_name: str = Field(description="High-level category name")

    rationale: str | None = Field(
        default=None, description="Explanation of rubric design and stage structure"
    )

    max_total_score: float = Field(
        gt=0, description="Maximum possible total score across all stages"
    )

    stages: list[EvaluationStage] = Field(description="Evaluation stages in order", min_length=1)

    def validate_stages(self) -> None:
        """Validate that stages make sense."""
        total_max = sum(stage.max_points for stage in self.stages)
        if total_max > self.max_total_score:
            raise ValueError(
                f"Sum of stage max points ({total_max}) exceeds "
                f"category max ({self.max_total_score})"
            )


class GDPEvalStagedRubric(BaseModel):
    """Wrapper for GDPEval task rubric with staged evaluation."""

    task_id: str = Field(description="GDPEval task ID")
    rubric: StagedRubric = Field(description="Staged rubric")
