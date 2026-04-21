"""Inngest-backed criterion executor: runs criteria in parallel via step.run."""

from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING
from uuid import UUID

import inngest
from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult, WorkerOutput
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.core.runtime.evaluation.criterion_runtime import DefaultCriterionRuntime
from ergon_core.core.runtime.evaluation.evaluation_schemas import (
    CriterionContext,
    CriterionSpec,
    TaskEvaluationContext,
)
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    TraceSink,
    evaluation_criterion_context,
    get_trace_sink,
)

if TYPE_CHECKING:
    from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


class InngestCriterionExecutor:
    """Executes criteria in parallel using Inngest step.run boundaries."""

    def __init__(
        self,
        ctx: inngest.Context,
        *,
        task_id: UUID,
        execution_id: UUID,
        evaluator_id: UUID,
        sandbox_manager: "BaseSandboxManager",
        trace_sink: TraceSink | None = None,
    ):
        self.ctx = ctx
        self.task_id = task_id
        self.execution_id = execution_id
        self.evaluator_id = evaluator_id
        self.sandbox_manager = sandbox_manager
        self._sink = trace_sink or get_trace_sink()

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        benchmark_name: str,
        criteria: list[CriterionSpec],
    ) -> list[CriterionResult]:
        def make_step(spec: CriterionSpec):
            async def run_criterion() -> CriterionResult:
                span_start = datetime.now(UTC)
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
                cr_result: CriterionResult

                runtime = DefaultCriterionRuntime(
                    context=criterion_context,
                    sandbox_manager=self.sandbox_manager,
                    run_id=task_context.run_id,
                    task_id=self.task_id,
                )

                if isinstance(criterion, Criterion):
                    eval_ctx = EvaluationContext(
                        run_id=task_context.run_id,
                        task_id=self.task_id,
                        execution_id=self.execution_id,
                        task=BenchmarkTask(
                            task_slug="",
                            instance_key="",
                            description=task_context.task_input,
                        ),
                        worker_result=WorkerOutput(
                            output=task_context.agent_reasoning,
                        ),
                        sandbox_id=task_context.sandbox_id or None,
                        runtime=runtime,
                    )
                    cr_result = await criterion.evaluate(eval_ctx)
                else:
                    try:
                        cr_result = await criterion.evaluate(runtime, criterion_context)
                    finally:
                        await runtime.cleanup()

                self._sink.emit_span(
                    CompletedSpan(
                        name="evaluation.criterion",
                        context=evaluation_criterion_context(
                            task_context.run_id,
                            self.task_id,
                            self.execution_id,
                            self.evaluator_id,
                            spec.stage_idx,
                            spec.criterion_idx,
                        ),
                        start_time=span_start,
                        end_time=datetime.now(UTC),
                        attributes={
                            "run_id": str(task_context.run_id),
                            "task_id": str(self.task_id),
                            "evaluator_id": str(self.evaluator_id),
                            "stage_idx": spec.stage_idx,
                            "criterion_idx": spec.criterion_idx,
                            "criterion_type": type(criterion).__name__,
                            "score": cr_result.score,
                            "max_score": spec.max_score,
                            "passed": cr_result.passed,
                        },
                    )
                )

                return cr_result

            step_name = f"criterion-{spec.stage_idx}-{spec.criterion_idx}"
            return partial(
                self.ctx.step.run,
                step_name,
                run_criterion,
                output_type=CriterionResult,
            )

        steps = tuple(make_step(spec) for spec in criteria)
        if not steps:
            return []

        results = await self.ctx.group.parallel(steps)
        return list(results)
