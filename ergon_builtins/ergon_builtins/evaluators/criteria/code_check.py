"""Code-check evaluation criterion."""

from typing import ClassVar

from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.api.sandbox import Sandbox


class CodeCheckCriterion(Criterion):
    """Code-based evaluation criterion inspired by the ref CodeRule.

    Holds a Python ``code_template`` that, when executed against the worker
    output, produces a score.  The lightweight ``evaluate()`` path runs a
    simple non-empty-output check suitable for smoke tests; the real sandbox
    execution path is wired through the Inngest criterion executor.
    """

    type_slug: ClassVar[str] = "code-check"

    code_template: str
    max_score: float = 1.0

    def __init__(
        self,
        *,
        slug: str,
        code_template: str,
        description: str = "",  # slopcop: ignore[no-str-empty-default]
        max_score: float = 1.0,
    ) -> None:
        super().__init__(
            slug=slug,
            description=description or slug,
            code_template=code_template,
            max_score=max_score,
        )

    async def evaluate(self, context: CriterionContext, *, sandbox: Sandbox) -> CriterionOutcome:
        output = context.worker_result.output
        passed = bool(output and len(output.strip()) > 0)
        score = self.max_score if passed else 0.0
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
            score=score,
            passed=passed,
            max_score=self.max_score,
            feedback=f"Code check '{self.slug}': {'passed' if passed else 'failed'}",
        )
