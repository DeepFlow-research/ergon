"""Single criterion evaluation Inngest function.

This function evaluates a single criterion against task outputs.
It's a leaf module with minimal dependencies to avoid circular imports.
"""

from uuid import UUID

import inngest

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import get_sandbox_manager
from h_arcane.core._internal.db.models import CriterionResult
from h_arcane.core._internal.evaluation.runner import EvaluationRunner
from h_arcane.core._internal.evaluation.schemas import EvaluationData
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client

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
    - rule: AnyRule auto-selects correct type via discriminator

    Note: criteria_evaluator is currently only used for GDPEval (staged rubrics
    with code/LLM rules). The sandbox manager is hardcoded for now but could
    be made generic via registry if other benchmarks need staged evaluation.
    """
    # Import here to avoid circular import - events.py imports types.py which imports rubric.py
    from h_arcane.core._internal.evaluation.events import CriterionEvaluationEvent

    payload = CriterionEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)

    data = EvaluationData(
        run_id=run_id,
        task_input=payload.task_input,
        agent_reasoning=payload.agent_reasoning,
        agent_outputs=payload.agent_outputs,
        stage_idx=payload.stage_idx,
        stage_name=payload.stage_name,
        rule_idx=payload.rule_idx,
        max_score=payload.max_score,
    )

    # Create sandbox manager dynamically from benchmark registry
    benchmark_name = BenchmarkName(payload.benchmark_name)
    sandbox_manager = get_sandbox_manager(benchmark_name)
    runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=ctx)

    result = await payload.rule.evaluate(runner)

    async def cleanup() -> None:
        await runner.cleanup()

    await ctx.step.run("cleanup", cleanup)

    return result
