"""Public fixed-criteria rubric implementation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, SerializeAsAny, field_validator

from ergon_core.api.criterion.criterion import Criterion
from ergon_core.api.criterion.results import CriterionOutcome
from ergon_core.api.evaluator import Evaluator
from ergon_core.api.rubric.results import TaskEvaluationResult
from ergon_core.core.domain.definitions import has_definition_type, inflate_definition

if TYPE_CHECKING:
    from ergon_core.api.benchmark.task import Task


class WeightedCriterion(BaseModel):
    """Criterion plus its aggregation weight."""

    model_config = {"arbitrary_types_allowed": True, "frozen": True}

    criterion: SerializeAsAny[Criterion]
    weight: float = 1.0

    @field_validator("criterion", mode="before")
    @classmethod
    def _inflate_criterion(cls, value: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if has_definition_type(value):
            return inflate_definition(value)
        return value

class Rubric(Evaluator):
    """Concrete evaluator with a fixed criteria list."""

    type_slug = "rubric"

    criteria: tuple[SerializeAsAny[WeightedCriterion], ...]

    @field_validator("criteria", mode="before", check_fields=False)
    @classmethod
    def _inflate_criteria(cls, value: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if isinstance(value, (list, tuple)):
            return tuple(
                WeightedCriterion.model_validate(item)
                if isinstance(item, dict) and "criterion" in item
                else item
                for item in value
            )
        return value

    def __init__(
        self,
        *,
        name: str,
        criteria: Iterable[WeightedCriterion | Criterion],
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
        **data: Any,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name,
            metadata=metadata,
            criteria=tuple(_as_weighted_criterion(criterion) for criterion in criteria),
            **data,
        )

    def criteria_for(self, task: Task) -> Iterable[Criterion]:
        return tuple(weighted.criterion for weighted in self.criteria)

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

        weighted_results = _results_with_configured_weights(results, self.criteria)
        total_weight = sum(r.weight for r in weighted_results)
        if total_weight == 0:
            weighted_score = 0.0
        else:
            weighted_score = sum(r.score * r.weight for r in weighted_results) / total_weight

        return TaskEvaluationResult(
            task_slug=task.task_slug,
            score=weighted_score,
            passed=all(r.passed for r in weighted_results),
            evaluator_name=self.name,
            criterion_results=weighted_results,
        )

    def validate(self) -> None:
        super().validate()
        for weighted in self.criteria:
            weighted.criterion.validate()


def _as_weighted_criterion(value: WeightedCriterion | Criterion) -> WeightedCriterion:
    if isinstance(value, WeightedCriterion):
        return value
    return WeightedCriterion(criterion=value, weight=value.weight)


def _results_with_configured_weights(
    results: list[CriterionOutcome],
    criteria: tuple[WeightedCriterion, ...],
) -> list[CriterionOutcome]:
    weights_by_slug = {weighted.criterion.slug: weighted.weight for weighted in criteria}
    return [
        result.model_copy(update={"weight": weights_by_slug.get(result.slug, result.weight)})
        for result in results
    ]
