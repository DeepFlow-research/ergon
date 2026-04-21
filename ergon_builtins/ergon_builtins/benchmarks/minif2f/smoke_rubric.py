"""Smoke rubric wrapping MiniF2FSmokeCriterion for the canonical 9-subtask smoke."""

from typing import ClassVar

from ergon_core.api.evaluator import Rubric

from ergon_builtins.evaluators.criteria.smoke_criterion import (
    MiniF2FSmokeCriterion,
)


class MiniF2FSmokeRubric(Rubric):
    """Rubric wrapping the minif2f env smoke criterion."""

    type_slug: ClassVar[str] = "minif2f-smoke-rubric"

    def __init__(self, *, name: str = "minif2f-smoke-rubric") -> None:
        super().__init__(
            name=name,
            criteria=[
                MiniF2FSmokeCriterion(
                    name="minif2f-smoke",
                    weight=1.0,
                ),
            ],
        )
