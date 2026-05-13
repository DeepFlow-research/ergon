"""Evaluator rubric for SWE-Bench Verified."""

from typing import ClassVar

from pydantic import Field

from ergon_core.api.criterion import Criterion
from ergon_core.api.rubric import Rubric

from ergon_builtins.benchmarks.swebench_verified.criterion import (
    SWEBenchTestCriterion,
)


class SWEBenchRubric(Rubric):
    """Rubric wrapping the SWE-Bench test-resolution criterion."""

    type_slug: ClassVar[str] = "swebench-rubric"
    name: str = "swebench-rubric"
    criteria: tuple[Criterion, ...] = Field(
        default_factory=lambda: (SWEBenchTestCriterion(slug="test-resolution", weight=1.0),),
        exclude=True,
    )
