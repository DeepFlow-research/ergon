"""GDPEval staged rubric with sequential gating aggregation.

The ``StagedRubric`` extends :class:`ergon_core.api.evaluator.Rubric` to
support multi-stage evaluation where each stage can gate subsequent
stages.  Stages are evaluated in order; a required stage whose score
falls below ``min_score_to_pass`` triggers the configured failure action
(skip remaining stages, zero the category, or continue).
"""

import logging
from collections.abc import Iterable
from typing import ClassVar, Literal

from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluator import Rubric
from ergon_core.api.results import CriterionResult, TaskEvaluationResult
from ergon_core.api.task_types import BenchmarkTask
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage model
# ---------------------------------------------------------------------------


class EvaluationStage(BaseModel):
    """Sequential stage in the evaluation pipeline.

    Each stage can act as a gate (must pass to continue), be optional
    (failure doesn't block), or simply contribute to the total score.
    """

    model_config = {"arbitrary_types_allowed": True}

    name: str = Field(description="Stage name (e.g. 'Format Validation Gate')")
    description: str = Field(description="What this stage evaluates")

    is_required: bool = Field(
        default=True,
        description="Must pass this stage to proceed to next stages",
    )

    max_points: float = Field(gt=0, description="Maximum points for this stage")

    min_score_to_pass: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Minimum absolute score to pass.  Must be <= max_points.  "
            "Auto-corrected to 25%% of max_points when violated."
        ),
    )

    criteria: list[Criterion] = Field(
        description="Criteria evaluated in this stage",
        min_length=1,
    )

    on_failure_action: Literal["skip_remaining", "zero_category", "continue"] = Field(
        default="skip_remaining",
        description=(
            "Action when stage fails: "
            "'skip_remaining' stops evaluation; "
            "'zero_category' replaces category score with on_failure_score; "
            "'continue' proceeds to next stage."
        ),
    )

    on_failure_score: float = Field(
        default=0.0,
        description="Score substituted when on_failure_action='zero_category'",
    )

    @model_validator(mode="after")
    def _validate_min_score(self) -> "EvaluationStage":
        if self.min_score_to_pass > self.max_points:
            original = self.min_score_to_pass
            self.min_score_to_pass = self.max_points * 0.25
            logger.warning(
                "Auto-corrected min_score_to_pass: %.1f > max_points (%.1f). "
                "Set to %.1f (25%% of max_points) for stage '%s'",
                original,
                self.max_points,
                self.min_score_to_pass,
                self.name,
            )
        return self


# ---------------------------------------------------------------------------
# Staged rubric
# ---------------------------------------------------------------------------


class StagedRubric(Rubric):
    """Rubric with sequential evaluation stages and gating logic.

    Evaluation proceeds through stages in declaration order:

    1. Evaluate all criteria in the stage.
    2. Sum their scores (capped at ``stage.max_points``).
    3. If the sum < ``stage.min_score_to_pass`` *and* the stage is
       required, apply the configured ``on_failure_action``.
    4. Otherwise continue to the next stage.

    The final score is the sum of all evaluated stages, normalised
    against ``max_total_score``.
    """

    type_slug: ClassVar[str] = "gdpeval-staged-rubric"

    def __init__(
        self,
        *,
        category_name: str,
        max_total_score: float,
        stages: list[EvaluationStage],
        rationale: str | None = None,
        name: str = "gdpeval-staged-rubric",
    ) -> None:
        all_criteria: list[Criterion] = []
        criterion_stage_map: dict[str, int] = {}

        for stage_idx, stage in enumerate(stages):
            for criterion in stage.criteria:
                all_criteria.append(criterion)
                criterion_stage_map[criterion.name] = stage_idx

        super().__init__(name=name, criteria=all_criteria)

        self.category_name = category_name
        self.max_total_score = max_total_score
        self.stages = list(stages)
        self.rationale = rationale
        self._criterion_stage_map = criterion_stage_map

        total_stage_max = sum(s.max_points for s in stages)
        if total_stage_max > max_total_score:
            raise ValueError(
                f"Sum of stage max_points ({total_stage_max}) exceeds "
                f"max_total_score ({max_total_score})"
            )

    # -- Rubric interface overrides ----------------------------------------

    def aggregate_task(
        self,
        task: BenchmarkTask,
        criterion_results: Iterable[CriterionResult],
    ) -> TaskEvaluationResult:
        results = list(criterion_results)
        stage_results = self._rebuild_stage_results(results)

        total_score = 0.0
        stages_evaluated = 0
        stages_passed = 0
        failed_gate: str | None = None

        for stage_idx, sr in enumerate(stage_results):
            stages_evaluated += 1
            total_score += sr["score"]
            stage = self.stages[stage_idx]

            if sr["passed"]:
                stages_passed += 1
                continue

            if stage.is_required and failed_gate is None:
                failed_gate = stage.name

            if stage.on_failure_action == "skip_remaining":
                break
            elif stage.on_failure_action == "zero_category":
                total_score -= sr["score"]
                total_score += stage.on_failure_score

        normalized = (
            min(max(total_score / self.max_total_score, 0.0), 1.0)
            if self.max_total_score > 0
            else 0.0
        )

        metadata: dict = {
            "stages_evaluated": stages_evaluated,
            "stages_passed": stages_passed,
            "max_total_score": self.max_total_score,
            "category_name": self.category_name,
        }
        if failed_gate is not None:
            metadata["failed_gate"] = failed_gate
        if self.rationale:
            metadata["rationale"] = self.rationale

        return TaskEvaluationResult(
            task_key=task.task_key,
            score=normalized,
            passed=failed_gate is None,
            evaluator_name=self.name,
            criterion_results=results,
            feedback=self._build_feedback(stages_evaluated, stages_passed, failed_gate),
            metadata=metadata,
        )

    def validate(self) -> None:
        super().validate()
        if not self.stages:
            raise ValueError("StagedRubric must have at least one stage")
        for stage in self.stages:
            if not stage.criteria:
                raise ValueError(f"Stage '{stage.name}' has no criteria")

    # -- internal helpers ---------------------------------------------------

    def _rebuild_stage_results(self, criterion_results: list[CriterionResult]) -> list[dict]:
        stage_results: list[dict] = []
        for stage_idx, stage in enumerate(self.stages):
            stage_criteria = [
                cr
                for cr in criterion_results
                if self._criterion_stage_map.get(cr.name) == stage_idx
            ]
            score = min(sum(cr.score for cr in stage_criteria), stage.max_points)
            stage_results.append(
                {
                    "stage_idx": stage_idx,
                    "stage_name": stage.name,
                    "score": score,
                    "max_points": stage.max_points,
                    "passed": score >= stage.min_score_to_pass,
                    "criteria": [
                        {
                            "name": cr.name,
                            "score": cr.score,
                            "weight": cr.weight,
                            "passed": cr.passed,
                            "feedback": cr.feedback,
                        }
                        for cr in stage_criteria
                    ],
                }
            )
        return stage_results

    @staticmethod
    def _build_feedback(
        stages_evaluated: int,
        stages_passed: int,
        failed_gate: str | None,
    ) -> str:
        parts = [f"Evaluated {stages_evaluated} stage(s), {stages_passed} passed."]
        if failed_gate:
            parts.append(f"Failed required gate: '{failed_gate}'.")
        return " ".join(parts)
