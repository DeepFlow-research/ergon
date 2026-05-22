"""Tests for GDPEval staged-rubric validation boundaries."""

import pytest
from pydantic import ValidationError

from ergon_builtins.benchmarks.gdpeval.rubric.staged_rubric import (
    EvaluationStage,
    StagedRubric,
)
from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome


class _Criterion(Criterion):
    type_slug = "gdpeval-test-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(slug=self.slug, score=1.0, passed=True)


def test_staged_rubric_does_not_override_runtime_dependency_validation() -> None:
    assert "validate_runtime_deps" not in StagedRubric.__dict__


def test_stage_requires_criteria_at_model_boundary() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        EvaluationStage(
            name="Gate",
            description="Must have criteria.",
            max_points=1.0,
            criteria=[],
        )


def test_staged_rubric_materialises_criteria_from_stages() -> None:
    criterion = _Criterion(slug="gate")
    rubric = StagedRubric(
        category_name="quality",
        max_total_score=1.0,
        stages=[
            EvaluationStage(
                name="Gate",
                description="Gate criteria.",
                max_points=1.0,
                criteria=[criterion],
            )
        ],
    )

    assert rubric.criteria == (criterion,)
