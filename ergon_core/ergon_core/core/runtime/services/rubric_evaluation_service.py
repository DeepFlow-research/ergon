"""Service for evaluating a task using a criterion executor + evaluator.

Bridges between the Inngest evaluation functions and the public
Evaluator/Rubric API. Calls executor.execute_all() then evaluator.aggregate_task().

Returns both the public TaskEvaluationResult and the CriterionSpecs
so the persistence layer can build a fully-typed EvaluationSummary.
"""

from ergon_core.api.evaluator import Evaluator
from ergon_core.api.results import CriterionResult, TaskEvaluationResult
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.core.runtime.evaluation.evaluation_schemas import (
    CriterionSpec,
    TaskEvaluationContext,
)
from ergon_core.core.runtime.evaluation.executors import CriterionExecutor
from pydantic import BaseModel


class EvaluationServiceResult(BaseModel):
    """Internal result carrying both the public evaluation + spec metadata."""

    result: TaskEvaluationResult
    specs: list[CriterionSpec]


class RubricEvaluationService:
    """Runs evaluation: execute criteria then aggregate via the evaluator."""

    def __init__(self, criterion_executor: CriterionExecutor):
        self.criterion_executor = criterion_executor

    async def evaluate(
        self,
        task_context: TaskEvaluationContext,
        evaluator: Evaluator,
        task: BenchmarkTask,
        benchmark_name: str,
    ) -> EvaluationServiceResult:
        criteria = list(evaluator.criteria_for(task))

        specs = [
            CriterionSpec(
                criterion=c,
                criterion_idx=i,
                max_score=c.weight,
                stage_idx=0,
                stage_name="default",
                aggregation_weight=c.weight,
            )
            for i, c in enumerate(criteria)
        ]

        criterion_results: list[CriterionResult] = await self.criterion_executor.execute_all(
            task_context=task_context,
            benchmark_name=benchmark_name,
            criteria=specs,
        )

        task_result = evaluator.aggregate_task(task, criterion_results)
        return EvaluationServiceResult(result=task_result, specs=specs)
