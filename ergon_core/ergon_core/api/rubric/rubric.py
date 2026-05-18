"""Public fixed-criteria rubric implementation."""

from collections.abc import Iterable
from typing import Any, ClassVar

from pydantic import Field, field_serializer, field_validator

from ergon_core.api.benchmark.task import Task
from ergon_core.api.criterion.criterion import Criterion
from ergon_core.api.criterion.outcome import CriterionOutcome
from ergon_core.api.rubric.evaluator import Evaluator
from ergon_core.api.rubric.results import TaskEvaluationResult


class Rubric(Evaluator):
    """Core public API generic fixed-criteria Evaluator.

    Rubric intentionally lives in ``ergon_core.api`` rather than builtins:
    it is the reusable author-facing Evaluator for benchmarks whose criteria
    are known up front, while builtins own only benchmark-specific criteria.
    """

    type_slug: ClassVar[str] = "rubric"

    criteria: tuple[Criterion, ...] = Field(default_factory=tuple)

    @field_serializer("criteria")
    def _serialize_criteria(self, criteria: tuple[Criterion, ...]) -> list[dict[str, Any]]:
        return [criterion.model_dump(mode="json") for criterion in criteria]

    @field_validator("criteria", mode="before")
    @classmethod
    def _rehydrate_criteria(
        cls, value: Any
    ) -> tuple[Criterion, ...]:
        if value is None:
            return ()
        return tuple(
            Criterion.from_definition(item) if isinstance(item, dict) else item for item in value
        )

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

    def validate_runtime_deps(self) -> None:
        super().validate_runtime_deps()
        for criterion in self.criteria:
            criterion.validate()
