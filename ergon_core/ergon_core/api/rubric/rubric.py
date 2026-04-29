"""Public fixed-criteria rubric implementation."""

from collections.abc import Iterable, Mapping
from typing import Any

from ergon_core.api.benchmark.task import Task
from ergon_core.api.criterion.criterion import Criterion
from ergon_core.api.criterion.results import CriterionOutcome
from ergon_core.api.rubric.evaluator import Evaluator
from ergon_core.api.rubric.results import TaskEvaluationResult


class Rubric(Evaluator):
    """Concrete evaluator with a fixed criteria list."""

    def __init__(
        self,
        *,
        name: str,
        criteria: Iterable[Criterion],
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(name=name, metadata=metadata)
        self.criteria: tuple[Criterion, ...] = tuple(criteria)

    def criteria_for(self, task: Task) -> Iterable[Criterion]:
        return self.criteria

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

        total_weight = sum(r.weight for r in results)
        if total_weight == 0:
            weighted_score = 0.0
        else:
            weighted_score = sum(r.score * r.weight for r in results) / total_weight

        return TaskEvaluationResult(
            task_slug=task.task_slug,
            score=weighted_score,
            passed=all(r.passed for r in results),
            evaluator_name=self.name,
            criterion_results=results,
        )

    def validate(self) -> None:
        super().validate()
        for criterion in self.criteria:
            criterion.validate()
