"""Public fixed-criteria rubric implementation."""

from collections.abc import Iterable
from typing import ClassVar

from pydantic import Field

from ergon_core.api.benchmark.task import Task
from ergon_core.api.criterion.criterion import Criterion
from ergon_core.api.criterion.results import CriterionOutcome
from ergon_core.api.rubric.evaluator import Evaluator
from ergon_core.api.rubric.results import TaskEvaluationResult


class Rubric(Evaluator):
    """Concrete evaluator with a fixed criteria list."""

    type_slug: ClassVar[str] = "rubric"

    # Criteria are arbitrary types (each ``Criterion`` is a plain ABC,
    # not a Pydantic BaseModel — its config lives in subclass
    # ``__init__``). ``arbitrary_types_allowed`` on the ``Evaluator``
    # base permits this. ``exclude=True`` keeps criteria out of
    # ``model_dump`` because Criterion instances are not JSON-
    # serializable; subclass defaults rebuild the list on
    # ``model_validate``. PR 11 may tighten criteria to Pydantic too
    # once every criterion subclass is migrated.
    criteria: tuple[Criterion, ...] = Field(default_factory=tuple, exclude=True)

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
