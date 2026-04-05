"""Execution strategy abstractions for rubric evaluation."""

from __future__ import annotations

from typing import Protocol

from h_arcane.core._internal.db.models import CriterionResult
from h_arcane.core._internal.evaluation.schemas import CriterionSpec, TaskEvaluationContext


class CriterionExecutor(Protocol):
    """Executes a rubric's criteria according to some orchestration strategy."""

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        benchmark_name: str,
        criteria: list[CriterionSpec],
    ) -> list[CriterionResult]:
        ...
