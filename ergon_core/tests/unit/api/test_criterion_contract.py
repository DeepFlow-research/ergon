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
            slug=self.slug,
            name=self.slug,
            score=self.score_spec.max_score,
            passed=True,
        )


def test_criterion_requires_slug_keyword() -> None:
    with pytest.raises(ValidationError):
        _Criterion(name="old-name")  # type: ignore[call-arg]


def test_criterion_exposes_slug_and_score_spec_without_compatibility_aliases() -> None:
    criterion = _Criterion(
        slug="canonical-slug",
        score_spec=ScoreScale(max_score=2.5),
    )

    assert criterion.slug == "canonical-slug"
    assert criterion.score_spec.max_score == 2.5
    assert not hasattr(criterion, "name")
    assert not hasattr(criterion, "max_score")


def test_criterion_outcome_requires_slug_without_name_fallback() -> None:
    with pytest.raises(ValidationError):
        CriterionOutcome.model_validate({"name": "legacy-name", "score": 1.0, "passed": True})


def test_criterion_outcome_allows_slug_without_name() -> None:
    outcome = CriterionOutcome(slug="canonical-slug", score=1.0, passed=True)

    assert outcome.slug == "canonical-slug"
    assert outcome.name is None


def test_criterion_validates_dependencies_with_runtime_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[tuple[list[str], str]] = []

    def fake_check_packages(packages: list[str], owner: str) -> list[str]:
        checked.append((packages, owner))
        return []

    monkeypatch.setattr(
        "ergon_core.api.criterion.criterion.check_packages",
        fake_check_packages,
    )

    criterion = _Criterion(slug="canonical-slug")
    criterion.validate_runtime_deps()

    assert checked == [([], "Criterion 'test-criterion'")]
