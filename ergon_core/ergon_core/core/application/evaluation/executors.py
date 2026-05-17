"""Execution strategy abstractions for rubric evaluation."""

from typing import Protocol

from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.benchmark import Task
from ergon_core.core.application.evaluation.models import (
    CriterionSpec,
    TaskEvaluationContext,
)


# TODO: check if this even live anymore
class CriterionExecutor(Protocol):
    """Executes a rubric's criteria according to some orchestration strategy."""

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        task: Task,
        benchmark_name: str,
        criteria: list[CriterionSpec],
    ) -> list[CriterionOutcome]: ...
