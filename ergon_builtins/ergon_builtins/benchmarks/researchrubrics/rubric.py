"""ResearchRubrics rubric with WEIGHTED aggregation including negative weights.

Normalization formula::

    normalized_score = (total - min_possible) / (max_possible - min_possible)

where *total* is the sum of weights for criteria that passed, *max_possible*
is the sum of all positive weights, and *min_possible* is the sum of all
negative weights.
"""

from collections.abc import Iterable, Sequence
from typing import ClassVar

from ergon_core.api.evaluator import Rubric
from ergon_core.api.results import CriterionResult, TaskEvaluationResult
from ergon_core.api.task_types import BenchmarkTask

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

    def __init__(
        self,
        *,
        name: str = "researchrubrics-rubric",
        rubric_criteria: Sequence[RubricCriterion] = (),
    ) -> None:
        criteria = build_criteria_from_rubrics(list(rubric_criteria))
        super().__init__(name=name, criteria=criteria)
        self._rubric_criteria = tuple(rubric_criteria)

    def criteria_for(self, task: BenchmarkTask):
        """Build task-specific LLM-judge criteria from the task payload."""
        if self._rubric_criteria:
            return self.criteria

        payload = ResearchRubricsTaskPayload.model_validate(task.task_payload.model_dump())
        rubric_criteria = list(payload.rubrics)
        return build_criteria_from_rubrics(rubric_criteria)

    def aggregate_task(
        self,
        task: BenchmarkTask,
        criterion_results: Iterable[CriterionResult],
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
                "max_possible": max_possible,
                "min_possible": min_possible,
            },
        )
