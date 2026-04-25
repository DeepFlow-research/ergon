"""Execution strategy abstractions for rubric evaluation."""

from typing import Protocol

from ergon_core.api.results import CriterionResult
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.core.runtime.evaluation.evaluation_schemas import (
    CriterionSpec,
    TaskEvaluationContext,
)


class CriterionExecutor(Protocol):
    """Executes a rubric's criteria according to some orchestration strategy."""

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        task: BenchmarkTask,
        benchmark_name: str,
        criteria: list[CriterionSpec],
    ) -> list[CriterionResult]: ...
