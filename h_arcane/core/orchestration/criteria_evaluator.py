"""Criteria evaluator - Inngest function for rule evaluation.

The evaluation logic lives in the rule classes:
- h_arcane.core.evaluation.rules.CodeRule
- h_arcane.core.evaluation.rules.LLMJudgeRule

Design Decision: We pass inngest.Context to EvaluationRunner for step-level observability.
This couples the runner to Inngest, but:
- Inngest is our primary orchestration framework and we want granular step tracing
- If we need to swap orchestration frameworks later, we can introduce a StepRunner
  protocol that abstracts ctx.step.run() - EvaluationRunner would then accept
  StepRunner instead of inngest.Context.
"""

from uuid import UUID

import inngest

from h_arcane.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from h_arcane.core.db.models import CriterionResult
from h_arcane.core.evaluation.context import EvaluationData, EvaluationRunner
from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.orchestration.events import CriterionEvaluationEvent


@inngest_client.create_function(  # type: ignore[misc]
    fn_id="evaluate-criterion",
    trigger=inngest.TriggerEvent(event="criterion/evaluate"),
    retries=2,
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
    """
    event_data = CriterionEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(event_data.run_id)

    # Build evaluation data - all fields already deserialized by Pydantic
    data = EvaluationData(
        run_id=run_id,
        task_input=event_data.task_input,
        agent_reasoning=event_data.agent_reasoning,
        agent_outputs=event_data.agent_outputs,
        stage_idx=event_data.stage_idx,
        stage_name=event_data.stage_name,
        rule_idx=event_data.rule_idx,
        max_score=event_data.max_score,
    )

    # Create sandbox manager and runner with Inngest context for step tracing
    # criteria_evaluator is only used for GDPEval (staged rubrics with code/LLM rules)
    sandbox_manager = GDPEvalSandboxManager()
    runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=ctx)

    # Evaluate rule - granular steps are inside rule.evaluate()
    result = await event_data.rule.evaluate(runner)

    # Cleanup sandbox if we created one
    async def cleanup() -> dict:
        await runner.cleanup()
        return {"cleaned_up": True}

    await ctx.step.run("cleanup", cleanup)

    return result
