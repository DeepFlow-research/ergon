"""Lightweight timing evaluator for smoke root tasks."""

from collections.abc import Mapping
from typing import Any, ClassVar

from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.api.rubric import Rubric


class SmokePostRootTimingCriterion(Criterion):
    """Second root-task criterion; e2e asserts its persisted timestamp."""

    type_slug: ClassVar[str] = "smoke-post-root-timing-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
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
            criteria=[SmokePostRootTimingCriterion(slug="smoke-post-root-timing")],
            metadata=metadata,
        )
