"""Smoke-test rubric for researchrubrics: stub-report-exists criterion only.

Pairs with ``StubResearchRubricsWorker`` for CI / E2B smoke tests.
"""

from typing import ClassVar

from ergon_core.api.evaluator import Rubric

from ergon_builtins.evaluators.criteria.stub_report_exists import (
    StubReportExistsCriterion,
)


class ResearchRubricsSmokeRubric(Rubric):
    """Rubric that checks the stub worker wrote its report and it has expected fields."""

    type_slug: ClassVar[str] = "researchrubrics-smoke-rubric"

    def __init__(self, *, name: str = "researchrubrics-smoke-rubric") -> None:
        super().__init__(
            name=name,
            criteria=[
                StubReportExistsCriterion(
                    name="report-exists-with-sections",
                    weight=1.0,
                ),
            ],
        )
