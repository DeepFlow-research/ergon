"""ResearchRubrics domain package."""

from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)

__all__ = [
    "ResearchRubricsRubric",
    "ResearchRubricsTaskPayload",
    "RubricCriterion",
]
