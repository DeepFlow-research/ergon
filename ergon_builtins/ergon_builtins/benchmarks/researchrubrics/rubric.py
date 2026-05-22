"""ResearchRubrics rubric with WEIGHTED aggregation including negative weights.

Normalization formula::

    normalized_score = (total - min_possible) / (max_possible - min_possible)

where *total* is the sum of weights for criteria that passed, *max_possible*
is the sum of all positive weights, and *min_possible* is the sum of all
negative weights.
"""

from collections.abc import Iterable
from typing import ClassVar

from pydantic import model_validator

from ergon_core.api.benchmark import Task
from ergon_core.api.criterion import Criterion, CriterionOutcome
from ergon_core.api.rubric import Rubric, TaskEvaluationResult

from ergon_builtins.benchmarks.researchrubrics.criteria import build_criteria_from_rubrics
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)


class ResearchRubricsRubric(Rubric):
    """Rubric for weighted criteria evaluation with positive and negative weights.

    Unlike a simple weighted-average rubric, ResearchRubrics treats each
    criterion as pass/fail and uses the criterion weight (which may be
    negative) as a fixed contribution to the total score.
    """

    type_slug: ClassVar[str] = "researchrubrics-rubric"
    name: str = "researchrubrics-rubric"
    # Authoring-time rubric criteria carried as data. The compiled
    # ``criteria`` tuple (Criterion instances) is materialised in the
    # post-init validator below and excluded from serialization — only
    # the authored RubricCriterion data round-trips.
    rubric_criteria: tuple[RubricCriterion, ...] = ()

    @model_validator(mode="after")
    def _materialise_criteria(self) -> "ResearchRubricsRubric":
        if self.rubric_criteria and not self.criteria:
            self.criteria = tuple(build_criteria_from_rubrics(list(self.rubric_criteria)))
        return self

    def criteria_for(self, task: Task) -> Iterable[Criterion]:
        """Build task-specific LLM-judge criteria from the task payload."""
        if self.rubric_criteria:
            return self.criteria

        payload = ResearchRubricsTaskPayload.model_validate(task.task_payload.model_dump())
        rubric_criteria = list(payload.rubrics)
        return build_criteria_from_rubrics(rubric_criteria)

    def aggregate_task(
        self,
        task: Task,
        criterion_results: Iterable[CriterionOutcome],
    ) -> TaskEvaluationResult:
        results = list(criterion_results)
        if not results:
            return TaskEvaluationResult(
                task_slug=task.task_slug,
                score=0.0,
                passed=False,
                evaluator_name=self.name,
                criterion_results=results,
                feedback="No criterion results to aggregate.",
            )

        total_score = 0.0
        max_possible = 0.0
        min_possible = 0.0

        for result in results:
            weight = result.weight

            if result.score > 0:
                total_score += weight
            # else: criterion failed, contributes 0

            if weight > 0:
                max_possible += weight
            else:
                min_possible += weight

        score_range = max_possible - min_possible
        normalized_score = (total_score - min_possible) / score_range if score_range > 0 else 0.0

        return TaskEvaluationResult(
            task_slug=task.task_slug,
            score=normalized_score,
            passed=total_score > 0,
            evaluator_name=self.name,
            criterion_results=results,
            metadata={
                "total_score": total_score,
                "score_scale": "normalized_0_1",
                "raw_score": total_score,
                "max_possible": max_possible,
                "min_possible": min_possible,
            },
        )
