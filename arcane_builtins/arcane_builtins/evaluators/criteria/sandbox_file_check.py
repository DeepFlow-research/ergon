"""Criterion that verifies a marker file exists in the E2B sandbox.

Used by the smoke-test rubric for CI / E2E testing. Connects to the
worker's sandbox via sandbox_id and checks for the expected file.
"""

from __future__ import annotations

from h_arcane.api import Criterion, CriterionResult, EvaluationContext

MARKER_PATH = "/outputs/ci_marker.txt"
MARKER_CONTENT = "smoke-test-marker"


class SandboxFileCheckCriterion(Criterion):
    type_slug = "sandbox-file-check"

    def __init__(
        self,
        *,
        name: str = "sandbox-file-check",
        weight: float = 1.0,
        expected_path: str = MARKER_PATH,
        expected_content: str = MARKER_CONTENT,
    ) -> None:
        self.name = name
        self.weight = weight
        self.expected_path = expected_path
        self.expected_content = expected_content

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        if not context.sandbox_id:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback="No sandbox_id available — cannot check files",
            )

        try:
            from e2b_code_interpreter import AsyncSandbox
        except ImportError:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback="e2b_code_interpreter not installed",
            )

        try:
            sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)
            content = await sandbox.files.read(self.expected_path)

            if isinstance(content, bytes):
                content = content.decode("utf-8")

            found = self.expected_content in content
            return CriterionResult(
                name=self.name,
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
        except Exception as exc:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=f"Failed to read {self.expected_path}: {exc}",
            )
