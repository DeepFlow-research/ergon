"""Inngest-backed criterion executor."""

from __future__ import annotations

from functools import partial
from uuid import UUID

import inngest

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import get_sandbox_manager
from h_arcane.core._internal.db.models import CriterionResult
from h_arcane.core._internal.evaluation.executors import CriterionExecutor
from h_arcane.core._internal.evaluation.runtime import DefaultCriterionRuntime
from h_arcane.core._internal.evaluation.schemas import (
    CriterionContext,
    CriterionSpec,
    TaskEvaluationContext,
)
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    evaluation_criterion_context,
    get_trace_sink,
)
from h_arcane.core._internal.utils import utcnow


class InngestCriterionExecutor(CriterionExecutor):
    """Executes criteria in parallel using Inngest step.run boundaries."""

    def __init__(
        self,
        ctx: inngest.Context,
        *,
        task_id: UUID,
        execution_id: UUID,
        evaluator_id: UUID,
    ):
        self.ctx = ctx
        self.task_id = task_id
        self.execution_id = execution_id
        self.evaluator_id = evaluator_id

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        benchmark_name: str,
        criteria: list[CriterionSpec],
    ) -> list[CriterionResult]:
        sandbox_manager = get_sandbox_manager(BenchmarkName(benchmark_name))

        def make_step(spec: CriterionSpec):
            async def run_criterion() -> CriterionResult:
                started_at = utcnow()
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
                runtime = DefaultCriterionRuntime(
                    context=criterion_context,
                    sandbox_manager=sandbox_manager,
                )
                try:
                    result = await spec.criterion.evaluate(runtime, criterion_context)
                    get_trace_sink().emit_span(
                        CompletedSpan(
                            name="evaluation.criterion",
                            context=evaluation_criterion_context(
                                task_context.run_id,
                                self.task_id,
                                self.execution_id,
                                self.evaluator_id,
                                spec.stage_idx,
                                spec.criterion_idx,
                                attributes={"criterion_type": spec.criterion.type},
                            ),
                            start_time=started_at,
                            end_time=utcnow(),
                            attributes={
                                "stage_name": spec.stage_name,
                                "stage_idx": spec.stage_idx,
                                "criterion_idx": spec.criterion_idx,
                                "criterion_type": spec.criterion.type,
                                "score": result.score,
                                "max_score": result.max_score,
                                "feedback": result.feedback,
                                "success": result.error is None,
                            },
                            status_code="ok" if result.error is None else "error",
                            status_message=str(result.error) if result.error else None,
                        )
                    )
                    return result
                finally:
                    await runtime.cleanup()

            step_name = f"criterion-{spec.stage_idx}-{spec.criterion_idx}-{spec.criterion.type}"
            return partial(
                self.ctx.step.run,
                step_name,
                run_criterion,
                output_type=CriterionResult,
            )

        results = await self.ctx.group.parallel(tuple(make_step(spec) for spec in criteria))
        return list(results)
