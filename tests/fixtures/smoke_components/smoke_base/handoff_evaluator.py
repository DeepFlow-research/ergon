"""Dynamic smoke evaluator for the resource handoff consumer task."""

from typing import ClassVar

from pydantic import Field, model_validator

from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.api.rubric import Rubric
from tests.fixtures.smoke_components.smoke_base.constants import (
    EXPECTED_RESOURCE_HANDOFF,
    HANDOFF_RESOURCE_NAME,
)


class SmokeResourceHandoffCriterion(Criterion):
    """Assert the consumer leaf observed the producer handoff resource."""

    type_slug: ClassVar[str] = "smoke-resource-handoff-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        handoff_probe = context.worker_result.metadata.get("handoff_probe", {})
        passed = bool(
            handoff_probe.get("checked")
            and handoff_probe.get("ok")
            and handoff_probe.get("resource_name") == HANDOFF_RESOURCE_NAME
            and handoff_probe.get("producer_slug") == EXPECTED_RESOURCE_HANDOFF.producer_slug
        )
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
            score=1.0 if passed else 0.0,
            passed=passed,
            weight=self.weight,
            feedback="handoff resource was visible to consumer" if passed else repr(handoff_probe),
        )


class SmokeResourceHandoffRubric(Rubric):
    """Evaluator attached only to the dynamic handoff consumer task."""

    type_slug: ClassVar[str] = "smoke-resource-handoff-evaluator"
    name: str = "smoke-resource-handoff-evaluator"
    criteria: tuple[Criterion, ...] = Field(default_factory=tuple, exclude=True)

    @model_validator(mode="after")
    def _build_criterion(self) -> "SmokeResourceHandoffRubric":
        if not self.criteria:
            self.criteria = (SmokeResourceHandoffCriterion(slug="smoke-resource-handoff"),)
        return self
