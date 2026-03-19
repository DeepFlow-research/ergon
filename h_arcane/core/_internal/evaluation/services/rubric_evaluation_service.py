"""Service for evaluating a rubric using a criterion executor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from h_arcane.core._internal.evaluation.executors import CriterionExecutor
from h_arcane.core._internal.evaluation.schemas import TaskEvaluationContext

if TYPE_CHECKING:
    from h_arcane.benchmarks.types import AnyRubric


class RubricEvaluationService:
    """Runs rubric evaluation while leaving orchestration to an executor."""

    def __init__(self, criterion_executor: CriterionExecutor):
        self.criterion_executor = criterion_executor

    async def evaluate(
        self,
        task_context: TaskEvaluationContext,
        rubric: "AnyRubric",
    ):
        criterion_results = await self.criterion_executor.execute_all(
            task_context=task_context,
            benchmark_name=rubric.benchmark,
            criteria=rubric.criteria,
        )
        return rubric.aggregate(task_context, criterion_results)
