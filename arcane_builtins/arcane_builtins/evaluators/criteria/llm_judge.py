"""LLM-judge evaluation criterion.

Stores a prompt template for an LLM judge evaluation. In-process evaluation
does a simple success check; real LLM calls happen via
InngestCriterionExecutor + DefaultCriterionRuntime.
"""

from typing import ClassVar

from h_arcane.api.criterion import Criterion
from h_arcane.api.evaluation_context import EvaluationContext
from h_arcane.api.results import CriterionResult

class LLMJudgeCriterion(Criterion):
    """LLM-judge evaluation criterion inspired by the ref LLMJudgeRule.

    Holds a ``prompt_template`` that, when sent to an LLM judge model,
    produces a pass/fail verdict with reasoning.  The lightweight
    ``evaluate()`` path checks ``worker_result.success``; the full LLM
    path is wired through the Inngest criterion executor.
    """

    type_slug: ClassVar[str] = "llm-judge"

    def __init__(
        self,
        *,
        name: str,
        prompt_template: str,
        description: str = "",  # slopcop: ignore[no-str-empty-default]
        weight: float = 1.0,
        max_score: float = 1.0,
        model: str = "gpt-4o",
    ) -> None:
        super().__init__(name=name, weight=weight)
        self.prompt_template = prompt_template
        self.description = description
        self.max_score = max_score
        self.model = model

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        passed = context.worker_result.success
        score = self.max_score if passed else 0.0
        return CriterionResult(
            name=self.name,
            score=score,
            passed=passed,
            weight=self.weight,
            feedback=f"LLM judge '{self.name}': {'passed' if passed else 'failed'}",
        )
