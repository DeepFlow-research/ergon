"""Trace-check evaluation criterion.

Checks that the worker's execution trace contains expected action types.
"""

from typing import ClassVar

from h_arcane.api.criterion import Criterion
from h_arcane.api.evaluation_context import EvaluationContext
from h_arcane.api.results import CriterionResult, WorkerResult


class TraceCheckCriterion(Criterion):
    """Checks that expected action types appear in the worker's execution trace.

    Inspects ``worker_result.artifacts["actions"]`` for dicts with an
    ``action_type`` key matching the supplied *expected_actions* list.
    """

    type_slug: ClassVar[str] = "trace-check"

    def __init__(
        self,
        *,
        name: str,
        expected_actions: list[str],
        weight: float = 1.0,
        require_order: bool = False,
    ) -> None:
        super().__init__(name=name, weight=weight)
        self.expected_actions = list(expected_actions)
        self.require_order = require_order

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        result = context.worker_result
        observed = self._extract_action_types(result)

        if self.require_order:
            matched, missing = self._check_ordered(observed)
        else:
            matched, missing = self._check_unordered(observed)

        total = len(self.expected_actions)
        score = len(matched) / total if total else 0.0
        passed = len(missing) == 0

        feedback_parts = [f"{len(matched)}/{total} expected actions found"]
        if missing:
            feedback_parts.append(f"Missing: {', '.join(missing)}")

        return CriterionResult(
            name=self.name,
            score=score,
            passed=passed,
            weight=self.weight,
            feedback=". ".join(feedback_parts),
            metadata={
                "matched": matched,
                "missing": missing,
                "observed": observed,
            },
        )

    def _check_unordered(self, observed: list[str]) -> tuple[list[str], list[str]]:
        observed_set = set(observed)
        matched = [a for a in self.expected_actions if a in observed_set]
        missing = [a for a in self.expected_actions if a not in observed_set]
        return matched, missing

    def _check_ordered(self, observed: list[str]) -> tuple[list[str], list[str]]:
        matched: list[str] = []
        obs_idx = 0
        for expected in self.expected_actions:
            while obs_idx < len(observed):
                if observed[obs_idx] == expected:
                    matched.append(expected)
                    obs_idx += 1
                    break
                obs_idx += 1
        missing = [a for a in self.expected_actions if a not in matched]
        return matched, missing

    @staticmethod
    def _extract_action_types(result: WorkerResult) -> list[str]:
        """Pull action_type strings from the worker result artifacts."""
        actions = result.artifacts.get("actions")
        if not isinstance(actions, list):
            return []

        types: list[str] = []
        for action in actions:
            if isinstance(action, dict):
                at = action.get("action_type")
                if isinstance(at, str):
                    types.append(at)
        return types
