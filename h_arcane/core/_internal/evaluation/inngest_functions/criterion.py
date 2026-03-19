"""Single criterion evaluation Inngest function.

This function evaluates a single criterion against task outputs.
It's a leaf module with minimal dependencies to avoid circular imports.
"""

import inngest

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import get_sandbox_manager
from h_arcane.core._internal.db.models import CriterionResult
from h_arcane.core._internal.evaluation.runtime import DefaultCriterionRuntime
from h_arcane.core._internal.evaluation.schemas import CriterionContext
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    evaluation_criterion_context,
    get_trace_sink,
)
from h_arcane.core._internal.utils import require_not_none, utcnow

# Import CriterionEvaluationEvent lazily to avoid circular import
# The event is only needed when the function is called, not at module load time


@inngest_client.create_function(
    fn_id="evaluate-criterion",
    trigger=inngest.TriggerEvent(
        event="criterion/evaluate"
    ),  # Use string to avoid importing event class
    retries=0,
    concurrency=[inngest.Concurrency(limit=20, scope="fn")],
    output_type=CriterionResult,
)
async def evaluate_criterion_fn(
    ctx: inngest.Context,
) -> CriterionResult:
    """
    Evaluate a single criterion against task outputs.

    Pydantic handles deserialization automatically via model_validate():
    - agent_outputs: list[Resource] auto-deserialized
    - criterion: AnyCriterion auto-selects correct type via discriminator
    """
    # Import here to avoid circular import - events.py imports types.py which imports rubric.py
    from h_arcane.core._internal.evaluation.events import CriterionEvaluationEvent

    payload = CriterionEvaluationEvent.model_validate(ctx.event.data)
    run_id = payload.run_id
    task_id = payload.task_id
    execution_id = payload.execution_id
    evaluator_id = payload.evaluator_id

    criterion_context = CriterionContext(
        run_id=run_id,
        task_input=payload.task_input,
        agent_reasoning=payload.agent_reasoning,
        agent_outputs=payload.agent_outputs,
        stage_idx=payload.stage_idx,
        stage_name=payload.stage_name,
        criterion_idx=payload.criterion_idx,
        max_score=payload.max_score,
    )

    benchmark_name = BenchmarkName(payload.benchmark_name)
    sandbox_manager = get_sandbox_manager(benchmark_name)
    runtime = DefaultCriterionRuntime(criterion_context, sandbox_manager)

    async def run_criterion() -> CriterionResult:
        try:
            return await payload.criterion.evaluate(runtime, criterion_context)
        finally:
            await runtime.cleanup()

    started_at = utcnow()
    result = await ctx.step.run(
        f"criterion-{payload.stage_idx}-{payload.criterion_idx}-{payload.criterion.type}",
        run_criterion,
        output_type=CriterionResult,
    )
    result = require_not_none(result, "criterion step returned None")
    get_trace_sink().emit_span(
        CompletedSpan(
            name="evaluation.criterion",
            context=evaluation_criterion_context(
                run_id,
                task_id,
                execution_id,
                evaluator_id,
                payload.stage_idx,
                payload.criterion_idx,
                attributes={"criterion_type": payload.criterion.type},
            ),
            start_time=started_at,
            end_time=utcnow(),
            attributes={
                "stage_name": payload.stage_name,
                "stage_idx": payload.stage_idx,
                "criterion_idx": payload.criterion_idx,
                "criterion_type": payload.criterion.type,
                "score": result.score,
                "max_score": result.max_score,
                "feedback": result.feedback,
            },
            status_code="ok" if result.error is None else "error",
            status_message=str(result.error) if result.error else None,
        )
    )
    return result
