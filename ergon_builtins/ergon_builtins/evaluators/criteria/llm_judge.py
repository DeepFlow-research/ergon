"""Generic LLM-judge evaluation criterion.

This remains available for benchmark presets that want a lightweight judge,
but it owns its provider call directly instead of reaching through
``CriterionRuntime``. Benchmark-specific rubrics should prefer dedicated
criterion classes with their own prompts and evidence formatting.
"""

from typing import ClassVar

from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult
from ergon_core.core.providers.generation.structured_judge import (
    JudgeMessage,
    call_structured_judge,
)
from pydantic import BaseModel


class _JudgeVerdict(BaseModel):
    """Structured response expected from the LLM judge."""

    reasoning: str
    passed: bool


class LLMJudgeCriterion(Criterion):
    """LLM-judge evaluation criterion.

    Holds a ``prompt_template`` that, when sent to an LLM judge model,
    produces a pass/fail verdict with reasoning.
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
        messages = [
            JudgeMessage(role="system", content=self.prompt_template),
            JudgeMessage(
                role="user",
                content=(
                    f"Task input:\n{context.task.description}\n\n"
                    f"Worker output:\n{context.worker_result.output}"
                ),
            ),
        ]

        verdict: _JudgeVerdict = await call_structured_judge(
            messages=messages,
            response_type=_JudgeVerdict,
            model=self.model,
        )

        score = self.max_score if verdict.passed else 0.0
        return CriterionResult(
            name=self.name,
            score=score,
            passed=verdict.passed,
            weight=self.weight,
            feedback=verdict.reasoning,
        )
