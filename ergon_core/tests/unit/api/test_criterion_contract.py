"""Contracts for the public Criterion base class."""

import pytest

from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.sandbox import Sandbox
from pydantic import ValidationError


class _Criterion(Criterion):
    type_slug = "test-criterion"

    async def evaluate(self, context: CriterionContext, *, sandbox: Sandbox) -> CriterionOutcome:
        return CriterionOutcome(
            name=self.slug,
            score=1.0,
            passed=True,
        )


def test_criterion_requires_slug_keyword() -> None:
    with pytest.raises(ValidationError):
        _Criterion(name="legacy-name")  # type: ignore[call-arg]


def test_criterion_exposes_slug_without_scoring_configuration() -> None:
    criterion = _Criterion(
        slug="canonical-slug",
    )

    assert criterion.slug == "canonical-slug"
    assert not hasattr(criterion, "name")
    assert not hasattr(criterion, "max_score")
    assert not hasattr(criterion, "weight")
    assert not hasattr(criterion, "score_spec")


def test_criterion_uses_plain_model_field_defaults() -> None:
    criterion = _Criterion(slug="canonical-slug")

    assert criterion.description == ""
    assert criterion.metadata == {}
