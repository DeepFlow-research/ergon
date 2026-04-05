"""Inngest-backed criterion executor: runs criteria in parallel via step.run."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING
from uuid import UUID

import inngest
from h_arcane.api.criterion import Criterion
from h_arcane.api.evaluation_context import EvaluationContext
from h_arcane.api.results import CriterionResult, WorkerResult
from h_arcane.api.task_types import BenchmarkTask
from h_arcane.core.runtime.evaluation.criterion_runtime import DefaultCriterionRuntime
from h_arcane.core.runtime.evaluation.evaluation_schemas import (
    CriterionContext,
    CriterionSpec,
    TaskEvaluationContext,
)

if TYPE_CHECKING:
    from h_arcane.core.providers.sandbox.manager import BaseSandboxManager


class InngestCriterionExecutor:
    """Executes criteria in parallel using Inngest step.run boundaries."""

    def __init__(
        self,
        ctx: inngest.Context,
        *,
        task_id: UUID,
        execution_id: UUID,
        evaluator_id: UUID,
        sandbox_manager: BaseSandboxManager | None = None,
    ):
        self.ctx = ctx
        self.task_id = task_id
        self.execution_id = execution_id
        self.evaluator_id = evaluator_id
        self.sandbox_manager = sandbox_manager

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        benchmark_name: str,
        criteria: list[CriterionSpec],
    ) -> list[CriterionResult]:

        def make_step(spec: CriterionSpec):
            async def run_criterion() -> CriterionResult:
                criterion_context = CriterionContext(
                    run_id=task_context.run_id,
                    task_input=task_context.task_input,
                    agent_reasoning=task_context.agent_reasoning,
                    agent_outputs=task_context.agent_outputs,
                    stage_idx=spec.stage_idx,
                    stage_name=spec.stage_name,
                    criterion_idx=spec.criterion_idx,
                    max_score=spec.max_score,
                )

                criterion = spec.criterion

                if isinstance(criterion, Criterion):
                    eval_ctx = EvaluationContext(
                        run_id=task_context.run_id,
                        task=BenchmarkTask(
                            task_key="",
                            instance_key="",
                            description=task_context.task_input,
                        ),
                        worker_result=WorkerResult(
                            output=task_context.agent_reasoning,
                        ),
                        sandbox_id=None,
                        metadata={},
                    )
                    return await criterion.evaluate(eval_ctx)

                if self.sandbox_manager is not None:
                    runtime = DefaultCriterionRuntime(
                        context=criterion_context,
                        sandbox_manager=self.sandbox_manager,
                    )
                    try:
                        return await criterion.evaluate(runtime, criterion_context)
                    finally:
                        await runtime.cleanup()

                raise TypeError(
                    f"Criterion {type(criterion).__name__} is not a public Criterion ABC "
                    f"implementation and no sandbox_manager is available for internal criteria"
                )

            step_name = f"criterion-{spec.stage_idx}-{spec.criterion_idx}"
            return partial(
                self.ctx.step.run, step_name, run_criterion,
                output_type=CriterionResult,
            )

        steps = tuple(make_step(spec) for spec in criteria)
        if not steps:
            return []

        results = await self.ctx.group.parallel(steps)
        return list(results)
