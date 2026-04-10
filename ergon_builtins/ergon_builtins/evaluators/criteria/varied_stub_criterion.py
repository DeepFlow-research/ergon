"""Test fixture: returns random scores to produce reward variance for GRPO.

Use with ``varied-stub-rubric`` when testing the gradient pipeline.
Not meaningful for real evaluation.
"""

import random

from ergon_core.api import Criterion, CriterionResult, EvaluationContext


class VariedStubCriterion(Criterion):
    """Returns a random score between 0.1 and 1.0."""

    type_slug = "varied-stub-criterion"

    def __init__(self, *, name: str = "varied-stub-criterion", weight: float = 1.0) -> None:
        self.name = name
        self.weight = weight

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        score = random.uniform(0.1, 1.0)
        return CriterionResult(
            name=self.name,
            score=score,
            passed=score > 0.5,
            weight=self.weight,
            feedback=f"Random score: {score:.3f}",
        )
