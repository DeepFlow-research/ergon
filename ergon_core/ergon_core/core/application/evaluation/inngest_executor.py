"""Inngest-backed criterion executor: runs criteria in parallel via step.run."""

from datetime import UTC, datetime
from functools import partial
from uuid import UUID

import inngest
from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext as PublicCriterionContext
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.benchmark import Task
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import WorkerOutput
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

class InngestCriterionExecutor:
    """Executes criteria in parallel using Inngest step.run boundaries."""

    def __init__(
        self,
        ctx: inngest.Context,
        *,
        task_id: UUID,
        execution_id: UUID,
        evaluator_id: UUID | None,
        sandbox: Sandbox,
        trace_sink: TraceSink | None = None,
    ):
        self.ctx = ctx
        self.task_id = task_id
        self.execution_id = execution_id
        self.evaluator_id = evaluator_id
        self.sandbox = sandbox
        self._sink = trace_sink or get_trace_sink()

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        task: Task,
        benchmark_name: str,
        criteria: list[CriterionSpec],
    ) -> list[CriterionOutcome]:
        def make_step(spec: CriterionSpec):
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

                agent_reasoning = (
                    "" if task_context.agent_reasoning is None else task_context.agent_reasoning
                )

                if isinstance(criterion, Criterion):
                    eval_ctx = PublicCriterionContext(
                        run_id=task_context.run_id,
                        task_id=self.task_id,
                        execution_id=self.execution_id,
                        task=task,
                        worker_result=WorkerOutput(
                            output=agent_reasoning,
                        ),
                        sandbox_id=task_context.sandbox_id,
                    )
                    cr_result = await criterion.evaluate(eval_ctx, sandbox=self.sandbox)
                else:
                    cr_result = await criterion.evaluate(criterion_context)

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
