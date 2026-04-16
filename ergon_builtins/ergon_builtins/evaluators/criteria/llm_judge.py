"""LLM-judge evaluation criterion.

Stores a prompt template for an LLM judge evaluation.  When
``EvaluationContext.runtime`` is available (injected by the executor),
``evaluate()`` calls ``context.runtime.call_llm_judge(...)`` for a real
LLM verdict.  If no runtime is present, raises ``RuntimeError`` -- the
executor contract guarantees injection.
"""

from typing import ClassVar

from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult
from pydantic import BaseModel


class _JudgeVerdict(BaseModel):
    """Structured response expected from the LLM judge."""

    reasoning: str
    passed: bool


class LLMJudgeCriterion(Criterion):
    """LLM-judge evaluation criterion.

    Holds a ``prompt_template`` that, when sent to an LLM judge model,
    produces a pass/fail verdict with reasoning via
    ``context.runtime.call_llm_judge()``.
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
        if context.runtime is None:
            raise RuntimeError(
                "LLMJudgeCriterion requires EvaluationContext.runtime; "
                "InngestCriterionExecutor should have injected it."
            )

        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    f"Task input:\n{context.task.description}\n\n"
                    f"Worker output:\n{context.worker_result.output}"
                ),
            },
        ]

        verdict: _JudgeVerdict = await context.runtime.call_llm_judge(
            messages,
            _JudgeVerdict,
        )

        score = self.max_score if verdict.passed else 0.0
        return CriterionResult(
            name=self.name,
            score=score,
            passed=verdict.passed,
            weight=self.weight,
            feedback=verdict.reasoning,
        )
