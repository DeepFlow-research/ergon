"""ResearchRubrics rubric with WEIGHTED aggregation including negative weights.

Normalization formula::

    normalized_score = (total - min_possible) / (max_possible - min_possible)

where *total* is the sum of weights for criteria that passed, *max_possible*
is the sum of all positive weights, and *min_possible* is the sum of all
negative weights.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from h_arcane.api.evaluator import Rubric
from h_arcane.api.results import CriterionResult, TaskEvaluationResult
from h_arcane.api.task_types import BenchmarkTask

from arcane_builtins.benchmarks.researchrubrics.criteria import build_criteria_from_rubrics
from arcane_builtins.benchmarks.researchrubrics.task_schemas import RubricCriterion


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
        rubric_criteria: list[RubricCriterion],
        name: str = "researchrubrics-rubric",
    ) -> None:
        criteria = build_criteria_from_rubrics(rubric_criteria)
        super().__init__(name=name, criteria=criteria)
        self._rubric_criteria = rubric_criteria

    def aggregate_task(
        self,
        task: BenchmarkTask,
        criterion_results: Iterable[CriterionResult],
    ) -> TaskEvaluationResult:
        results = list(criterion_results)
        if not results:
            return TaskEvaluationResult(
                task_key=task.task_key,
                score=0.0,
                passed=False,
                evaluator_name=self.name,
                criterion_results=results,
                feedback="No criterion results to aggregate.",
            )

        total_score = 0.0
        max_possible = 0.0
        min_possible = 0.0

        for criterion, result in zip(self.criteria, results, strict=True):
            weight = criterion.weight

            if result.score > 0:
                total_score += weight
            # else: criterion failed, contributes 0

            if weight > 0:
                max_possible += weight
            else:
                min_possible += weight

        score_range = max_possible - min_possible
        normalized_score = (
            (total_score - min_possible) / score_range if score_range > 0 else 0.0
        )

        return TaskEvaluationResult(
            task_key=task.task_key,
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
