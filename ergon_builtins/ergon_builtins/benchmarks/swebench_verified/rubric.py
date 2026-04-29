"""Evaluator rubric for SWE-Bench Verified."""

from typing import ClassVar

from ergon_core.api.rubric import Rubric

from ergon_builtins.benchmarks.swebench_verified.criterion import (
    SWEBenchTestCriterion,
)


class SWEBenchRubric(Rubric):
    """Rubric wrapping the SWE-Bench test-resolution criterion."""

    type_slug: ClassVar[str] = "swebench-rubric"

    def __init__(self, *, name: str = "swebench-rubric") -> None:
        super().__init__(
            name=name,
            criteria=[SWEBenchTestCriterion(slug="test-resolution", weight=1.0)],
        )
