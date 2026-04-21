"""Smoke rubric wrapping SweBenchSmokeCriterion for the canonical 9-subtask smoke."""

from typing import ClassVar

from ergon_core.api.evaluator import Rubric

from ergon_builtins.evaluators.criteria.smoke_criterion import (
    SweBenchSmokeCriterion,
)


class SweBenchSmokeRubric(Rubric):
    """Rubric wrapping the swebench env smoke criterion."""

    type_slug: ClassVar[str] = "swebench-smoke-rubric"

    def __init__(self, *, name: str = "swebench-smoke-rubric") -> None:
        super().__init__(
            name=name,
            criteria=[
                SweBenchSmokeCriterion(
                    name="swebench-smoke",
                    weight=1.0,
                ),
            ],
        )
