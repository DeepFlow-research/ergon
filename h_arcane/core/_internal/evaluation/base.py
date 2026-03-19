"""Base protocols and abstractions for evaluation."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from h_arcane.core._internal.db.models import CriterionResult, TaskEvaluationResult
    from h_arcane.core._internal.evaluation.schemas import CriterionSpec, TaskEvaluationContext


class BaseRubric(Protocol):
    """Protocol for benchmark rubrics."""

    benchmark: str
    criteria: list["CriterionSpec"]

    def aggregate(
        self,
        context: "TaskEvaluationContext",
        criterion_results: list["CriterionResult"],
    ) -> "TaskEvaluationResult":
        """Aggregate criterion results into a task-level evaluation result."""
        ...
