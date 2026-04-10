"""Smoke-test rubric: verifies the worker wrote a marker file to the sandbox.

Pairs with SmokeTestWorker for CI / E2E integration tests. The criterion
connects to the same E2B sandbox and checks the file round-tripped.
"""

from typing import ClassVar

from h_arcane.api.evaluator import Rubric

from arcane_builtins.evaluators.criteria.sandbox_file_check import SandboxFileCheckCriterion

class SmokeTestRubric(Rubric):
    """Rubric that checks the smoke-test worker wrote its marker file."""

    type_slug: ClassVar[str] = "smoke-test-rubric"

    def __init__(self, *, name: str = "smoke-test-rubric") -> None:
        super().__init__(
            name=name,
            criteria=[
                SandboxFileCheckCriterion(
                    name="marker-file-exists",
                    weight=1.0,
                ),
            ],
        )
