"""Public evaluator ABC and Rubric concrete implementation."""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar

from h_arcane.api.criterion import Criterion
from h_arcane.api.results import CriterionResult, TaskEvaluationResult
from h_arcane.api.task_types import BenchmarkTask


class Evaluator(ABC):
    """Base class for all evaluators.

    Subclasses must set ``type_slug`` and implement ``criteria_for`` and
    ``aggregate_task``.
    """

    type_slug: ClassVar[str]

    def __init__(
        self,
        *,
        name: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.metadata: dict[str, Any] = dict(metadata or {})

    @abstractmethod
    def criteria_for(self, task: BenchmarkTask) -> Iterable[Criterion]:
        """Resolve the criterion set to run for *task*."""
        ...

    @abstractmethod
    def aggregate_task(
        self,
        task: BenchmarkTask,
        criterion_results: Iterable[CriterionResult],
    ) -> TaskEvaluationResult:
        """Aggregate criterion-level outputs into one task-level result."""
        ...

    def validate(self) -> None:
        """Cheap validation of evaluator configuration."""


class Rubric(Evaluator):
    """Concrete evaluator with a fixed criteria list.

    Aggregates scores using weighted averages.
    """

    def __init__(
        self,
        *,
        name: str,
        criteria: Iterable[Criterion],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name, metadata=metadata)
        self.criteria: tuple[Criterion, ...] = tuple(criteria)

    def criteria_for(self, task: BenchmarkTask) -> Iterable[Criterion]:
        return self.criteria

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

        total_weight = sum(r.weight for r in results)
        if total_weight == 0:
            weighted_score = 0.0
        else:
            weighted_score = sum(r.score * r.weight for r in results) / total_weight

        all_passed = all(r.passed for r in results)
        return TaskEvaluationResult(
            task_key=task.task_key,
            score=weighted_score,
            passed=all_passed,
            evaluator_name=self.name,
            criterion_results=results,
        )

    def validate(self) -> None:
        for criterion in self.criteria:
            criterion.validate()
