"""Code-check evaluation criterion.

Stores a Python code template that checks worker output. In-process evaluation
does simple template matching; full sandbox execution happens via
InngestCriterionExecutor + DefaultCriterionRuntime.
"""

from typing import ClassVar

from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult, CriterionScoreSpec


class CodeCheckCriterion(Criterion):
    """Code-based evaluation criterion inspired by the ref CodeRule.

    Holds a Python ``code_template`` that, when executed against the worker
    output, produces a score.  The lightweight ``evaluate()`` path runs a
    simple non-empty-output check suitable for smoke tests; the real sandbox
    execution path is wired through the Inngest criterion executor.
    """

    type_slug: ClassVar[str] = "code-check"

    def __init__(
        self,
        *,
        slug: str,
        code_template: str,
        description: str = "",  # slopcop: ignore[no-str-empty-default]
        weight: float = 1.0,
        max_score: float = 1.0,
    ) -> None:
        super().__init__(
            slug=slug,
            description=description or slug,
            weight=weight,
            score_spec=CriterionScoreSpec(max_score=max_score),
        )
        self.code_template = code_template

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        output = context.worker_result.output
        passed = bool(output and len(output.strip()) > 0)
        score = self.score_spec.max_score if passed else 0.0
        return CriterionResult(
            slug=self.slug,
            name=self.slug,
            score=score,
            passed=passed,
            weight=self.weight,
            max_score=self.score_spec.max_score,
            feedback=f"Code check '{self.slug}': {'passed' if passed else 'failed'}",
        )
