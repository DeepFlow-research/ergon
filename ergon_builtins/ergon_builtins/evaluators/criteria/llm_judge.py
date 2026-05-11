"""Generic LLM-judge evaluation criterion.

This remains available for benchmark presets that want a lightweight judge,
but it owns its provider call directly instead of reaching through
``CriterionRuntime``. Benchmark-specific rubrics should prefer dedicated
criterion classes with their own prompts and evidence formatting.
"""

from typing import ClassVar

from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.api.sandbox import Sandbox
from pydantic import BaseModel

from ergon_builtins.common.llm.structured_judge import (
    JudgeMessage,
    call_structured_judge,
)


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

    prompt_template: str
    model: str = "gpt-4o"
    max_score: float = 1.0

    def __init__(
        self,
        *,
        slug: str,
        prompt_template: str,
        description: str = "",  # slopcop: ignore[no-str-empty-default]
        max_score: float = 1.0,
        model: str = "gpt-4o",
    ) -> None:
        super().__init__(
            slug=slug,
            description=description or slug,
            prompt_template=prompt_template,
            model=model,
            max_score=max_score,
        )

    async def evaluate(self, context: CriterionContext, *, sandbox: Sandbox) -> CriterionOutcome:
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
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
            score=score,
            passed=verdict.passed,
            max_score=self.max_score,
            feedback=verdict.reasoning,
        )
