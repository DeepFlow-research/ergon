"""Criterion that verifies a marker file exists in the E2B sandbox.

Used by the smoke-test rubric for CI / E2E testing.
"""

from typing import ClassVar

from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome

MARKER_PATH = "/outputs/ci_marker.txt"
MARKER_CONTENT = "smoke-test-marker"


class SandboxFileCheckCriterion(Criterion):
    type_slug: ClassVar[str] = "sandbox-file-check"

    slug: str = "sandbox-file-check"
    expected_path: str = MARKER_PATH
    expected_content: str = MARKER_CONTENT

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        if not context.task.sandbox.is_live:
            return CriterionOutcome(
                slug=self.slug,
                name=self.slug,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback="No live sandbox available — cannot check files",
            )

        try:
            content = await context.task.sandbox.read_file(self.expected_path)

            if isinstance(content, bytes):
                content = content.decode("utf-8")

            found = self.expected_content in content
            return CriterionOutcome(
                slug=self.slug,
                name=self.slug,
                score=1.0 if found else 0.0,
                passed=found,
                weight=self.weight,
                feedback=(
                    f"Found expected content at {self.expected_path}"
                    if found
                    else f"Content mismatch at {self.expected_path}: "
                    f"expected '{self.expected_content}', got '{content[:100]}'"
                ),
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return CriterionOutcome(
                slug=self.slug,
                name=self.slug,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=f"Failed to read {self.expected_path}: {exc}",
            )
