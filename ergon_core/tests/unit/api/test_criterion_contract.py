"""Contracts for the public Criterion base class."""

import pytest
from pydantic import ValidationError

from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.criterion import CriterionOutcome, ScoreScale


class _Criterion(Criterion):
    type_slug = "test-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(
            name=self.slug,
            score=self.score_spec.max_score,
            passed=True,
        )


def test_criterion_requires_slug_keyword() -> None:
    # PR 10 Task 0: Criterion is a Pydantic BaseModel + ABC. Missing the
    # required ``slug`` field raises ``ValidationError`` (Pydantic) rather
    # than the v1 ``TypeError`` from a hand-rolled ``__init__``.
    with pytest.raises(ValidationError):
        _Criterion(name="legacy-name")  # type: ignore[call-arg]


def test_criterion_exposes_slug_and_score_spec_without_compatibility_aliases() -> None:
    criterion = _Criterion(
        slug="canonical-slug",
        score_spec=ScoreScale(max_score=2.5),
    )

    assert criterion.slug == "canonical-slug"
    assert criterion.score_spec.max_score == 2.5
    assert not hasattr(criterion, "name")
    assert not hasattr(criterion, "max_score")
