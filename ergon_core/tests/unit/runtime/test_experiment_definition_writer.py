from typing import ClassVar

from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.core.application.experiments.definition_writer import _criterion_snapshot_name


class _Criterion(Criterion):
    type_slug: ClassVar[str] = "ci-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(slug=self.slug, name=self.slug, score=1.0, passed=True)


def test_criterion_snapshot_uses_public_slug_not_missing_name_attribute() -> None:
    criterion = _Criterion(slug="ci-criterion-instance")

    assert _criterion_snapshot_name(criterion) == "ci-criterion-instance"
