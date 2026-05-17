"""Inngest-backed criterion executor: runs criteria in parallel via step.run."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING
from uuid import UUID

import inngest
from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext as PublicCriterionContext
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.benchmark import Task
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.application.evaluation.criterion_runtime import (
    CriterionRuntimeOptions,
    DefaultCriterionRuntime,
)
from ergon_core.core.application.evaluation.models import (
    CriterionContext as EngineCriterionContext,
    CriterionSpec,
    TaskEvaluationContext,
)
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    TraceSink,
    evaluation_criterion_context,
    get_trace_sink,
)

if TYPE_CHECKING:
    from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager


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
    ) -> None:
        self.ctx = ctx
        self.task_id = task_id
        self.execution_id = execution_id
        self.evaluator_id = evaluator_id
        self.sandbox_manager = sandbox_manager
        self._sink = trace_sink or get_trace_sink()

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        task: Task,
        benchmark_name: str,  # TODO: dead arg here. also it probs shouldn't need this at all.
        criteria: list[CriterionSpec],
    ) -> list[CriterionOutcome]:
        def make_step(spec: CriterionSpec) -> Callable[[], Awaitable[CriterionOutcome]]:
            async def run_criterion() -> CriterionOutcome:
                span_start = datetime.now(UTC)
                criterion_context = EngineCriterionContext(
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
                cr_result: CriterionOutcome

                runtime = DefaultCriterionRuntime(
                    context=criterion_context,
                    sandbox_manager=self.sandbox_manager,
                    options=CriterionRuntimeOptions(
                        run_id=task_context.run_id,
                        task_id=self.execution_id,
                        # Per RFC ``sandbox-lifetime-covers-criteria``: pass
                        # the task's sandbox_id so ensure_sandbox prefers
                        # ``manager.reconnect(sandbox_id)`` over constructing
                        # a fresh sandbox when running cross-process.
                        sandbox_id=task_context.sandbox_id,
                    ),
                )

                agent_reasoning = (
                    "" if task_context.agent_reasoning is None else task_context.agent_reasoning
                )  # TODO: "" fallback, bad! we need to not probs make task_context.agent_reasoning required and not optional (or if it is then make this also | None)

                if isinstance(criterion, Criterion):
                    eval_ctx = PublicCriterionContext.with_runtime(
                        run_id=task_context.run_id,
                        task_id=self.task_id,
                        execution_id=self.execution_id,
                        task=task,
                        worker_result=WorkerOutput(
                            output=agent_reasoning,
                        ),
                        runtime=runtime,
                        sandbox_id=task_context.sandbox_id,
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
                output_type=CriterionOutcome,
            )

        return list(await self.ctx.group.parallel(tuple(make_step(spec) for spec in criteria)))
