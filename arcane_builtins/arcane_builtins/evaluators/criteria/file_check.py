"""File-check evaluation criterion.

Checks that specific file patterns appear in the worker's output or artifacts.
"""

from __future__ import annotations

import fnmatch
from typing import ClassVar

from h_arcane.api.criterion import Criterion
from h_arcane.api.evaluation_context import EvaluationContext
from h_arcane.api.results import CriterionResult, WorkerResult


class FileCheckCriterion(Criterion):
    """Checks that expected files are referenced in the worker result.

    Looks for file path evidence in ``worker_result.output``,
    ``worker_result.artifacts``, and action logs.  Patterns use
    :func:`fnmatch.fnmatch` glob syntax.
    """

    type_slug: ClassVar[str] = "file-check"

    def __init__(
        self,
        *,
        name: str,
        file_patterns: list[str],
        weight: float = 1.0,
    ) -> None:
        super().__init__(name=name, weight=weight)
        self.file_patterns = list(file_patterns)

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        result = context.worker_result
        evidence = self._collect_file_evidence(result)

        matched: list[str] = []
        missing: list[str] = []
        for pattern in self.file_patterns:
            if any(fnmatch.fnmatch(path, pattern) for path in evidence):
                matched.append(pattern)
            else:
                missing.append(pattern)

        total = len(self.file_patterns)
        score = len(matched) / total if total else 0.0
        passed = len(missing) == 0

        feedback_parts = [f"{len(matched)}/{total} file patterns matched"]
        if missing:
            feedback_parts.append(f"Missing: {', '.join(missing)}")

        return CriterionResult(
            name=self.name,
            score=score,
            passed=passed,
            weight=self.weight,
            feedback=". ".join(feedback_parts),
            metadata={"matched": matched, "missing": missing},
        )

    @staticmethod
    def _collect_file_evidence(result: WorkerResult) -> set[str]:
        """Gather file-path-like strings from the worker result."""
        paths: set[str] = set()

        for token in result.output.split():
            stripped = token.strip("\"'`,;:()")
            if "/" in stripped or "." in stripped:
                paths.add(stripped)

        for key in ("files", "file_list", "created_files", "output_files"):
            file_list = result.artifacts.get(key)
            if isinstance(file_list, list):
                paths.update(str(f) for f in file_list)

        actions = result.artifacts.get("actions")
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    action_output = action.get("output", "")
                    if isinstance(action_output, str):
                        for token in action_output.split():
                            stripped = token.strip("\"'`,;:()")
                            if "/" in stripped:
                                paths.add(stripped)

        return paths
