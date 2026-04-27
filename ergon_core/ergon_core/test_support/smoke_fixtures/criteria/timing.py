"""Lightweight timing evaluator for smoke root tasks."""

from collections.abc import Mapping
from typing import Any, ClassVar

from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.evaluator import Rubric
from ergon_core.api.results import CriterionResult


class SmokePostRootTimingCriterion(Criterion):
    """Second root-task criterion; e2e asserts its persisted timestamp."""

    type_slug: ClassVar[str] = "smoke-post-root-timing-criterion"

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        return CriterionResult(
            name=self.name,
            score=1.0,
            passed=True,
            weight=self.weight,
            feedback="root timing marker criterion ran",
        )


class SmokePostRootTimingRubric(Rubric):
    """Evaluator wrapper for the smoke timing criterion."""

    type_slug: ClassVar[str] = "smoke-post-root-timing-criterion"

    def __init__(
        self,
        *,
        name: str,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name,
            criteria=[SmokePostRootTimingCriterion(name="smoke-post-root-timing")],
            metadata=metadata,
        )


__all__ = ["SmokePostRootTimingCriterion", "SmokePostRootTimingRubric"]
