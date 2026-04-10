"""TEST FIXTURE ONLY. Do not use as a template for real criteria.

Passes when worker reports success. For smoke tests only.
"""

from ergon_core.api import Criterion, CriterionResult, EvaluationContext


class StubCriterion(Criterion):
    type_slug = "stub-criterion"

    def __init__(self, *, name: str = "stub-criterion", weight: float = 1.0) -> None:
        self.name = name
        self.weight = weight

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        passed = context.worker_result.success
        return CriterionResult(
            name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            weight=self.weight,
            feedback=f"Stub criterion: {'passed' if passed else 'failed'}",
        )
