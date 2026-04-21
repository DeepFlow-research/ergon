"""Smoke rubric wrapping ResearchRubricsSmokeCriterion for the canonical 9-subtask smoke."""

from typing import ClassVar

from ergon_core.api.evaluator import Rubric

from ergon_builtins.evaluators.criteria.smoke_criterion import (
    ResearchRubricsSmokeCriterion,
)


class ResearchRubricsSmokeRubric(Rubric):
    """Rubric wrapping the researchrubrics env smoke criterion."""

    type_slug: ClassVar[str] = "researchrubrics-smoke-rubric"

    def __init__(self, *, name: str = "researchrubrics-smoke-rubric") -> None:
        super().__init__(
            name=name,
            criteria=[
                ResearchRubricsSmokeCriterion(
                    name="researchrubrics-smoke",
                    weight=1.0,
                ),
            ],
        )
