"""Generic LLM-judge evaluation criterion.

This remains available for benchmark presets that want a lightweight judge,
but it owns its provider call directly instead of reaching through
``public sandbox runtime``. Benchmark-specific rubrics should prefer dedicated
criterion classes with their own prompts and evidence formatting.
"""

from typing import ClassVar

from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from pydantic import BaseModel, ConfigDict

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
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False, extra="forbid")

    prompt_template: str
    model: str = "gpt-4o"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
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

        score = self.score_spec.max_score if verdict.passed else 0.0
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
            score=score,
            passed=verdict.passed,
            weight=self.weight,
            max_score=self.score_spec.max_score,
            feedback=verdict.reasoning,
        )
