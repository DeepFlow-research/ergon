"""Lightweight timing evaluator for smoke root tasks."""

from typing import ClassVar

from pydantic import Field, model_validator

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
    """Evaluator wrapper for the smoke timing criterion.

    PR 10a: migrated from custom ``__init__`` to pure-Pydantic
    ``Field(default_factory=tuple, exclude=True)`` + ``@model_validator``
    so the rubric round-trips through ``Evaluator.from_definition`` (the
    object-bound code path used by ``SweBenchSmokeTask.evaluators``).
    """

    type_slug: ClassVar[str] = "smoke-post-root-timing-criterion"
    name: str = "smoke-post-root-timing-criterion"
    criteria: tuple[Criterion, ...] = Field(default_factory=tuple, exclude=True)

    @model_validator(mode="after")
    def _build_criterion(self) -> "SmokePostRootTimingRubric":
        if not self.criteria:
            self.criteria = (SmokePostRootTimingCriterion(slug="smoke-post-root-timing"),)
        return self
