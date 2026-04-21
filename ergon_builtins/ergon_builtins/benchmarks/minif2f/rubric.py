"""MiniF2F rubric with proof-verification scoring.

Scoring logic::

    if score >= max_score  -> full pass  (normalized = 1.0)
    elif score > 0         -> partial credit  (partial_credit_for_syntax * max_score)
    else                   -> 0
"""

from collections.abc import Iterable
from typing import ClassVar

from ergon_core.api.evaluator import Rubric
from ergon_core.api.results import CriterionResult, TaskEvaluationResult
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.minif2f.criteria import build_proof_criterion


class MiniF2FRubric(Rubric):
    """Rubric for formal proof verification with partial-credit for valid syntax."""

    type_slug: ClassVar[str] = "minif2f-rubric"

    def __init__(
        self,
        *,
        name: str = "minif2f-rubric",
        max_score: float = 1.0,
        partial_credit_for_syntax: float = 0.2,
        problem_statement: str | None = None,
        ground_truth_proof: str | None = None,
    ) -> None:
        self._max_score = max_score
        self._partial_credit = partial_credit_for_syntax

        criterion = build_proof_criterion(
            max_score=max_score,
            problem_statement=problem_statement,
            ground_truth_proof=ground_truth_proof,
        )
        super().__init__(name=name, criteria=[criterion])

    def aggregate_task(
        self,
        task: BenchmarkTask,
        criterion_results: Iterable[CriterionResult],
    ) -> TaskEvaluationResult:
        results = list(criterion_results)
        if len(results) != 1:
            raise ValueError(
                f"MiniF2FRubric expects exactly 1 criterion result, got {len(results)}"
            )

        cr = results[0]

        if cr.score >= self._max_score:
            total_score = self._max_score
            passed = True
        elif cr.score > 0:
            total_score = self._partial_credit * self._max_score
            passed = False
        else:
            total_score = 0.0
            passed = False

        normalized = total_score / self._max_score if self._max_score > 0 else 0.0

        return TaskEvaluationResult(
            task_slug=task.task_slug,
            score=normalized,
            passed=passed,
            evaluator_name=self.name,
            criterion_results=results,
            feedback="Proof Verification" if not passed else None,
            metadata={
                "total_score": total_score,
                "max_score": self._max_score,
                "partial_credit_for_syntax": self._partial_credit,
            },
        )
