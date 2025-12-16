"""Criteria evaluator - Inngest function for rule evaluation.

The evaluation logic lives in the rule classes:
- h_arcane.evaluation.rules.CodeRule
- h_arcane.evaluation.rules.LLMJudgeRule

Design Decision: We pass inngest.Context to EvaluationRunner for step-level observability.
This couples the runner to Inngest, but:
- Inngest is our primary orchestration framework and we want granular step tracing
- If we need to swap orchestration frameworks later, we can introduce a StepRunner
  protocol that abstracts ctx.step.run() - EvaluationRunner would then accept
  StepRunner instead of inngest.Context.
"""

from uuid import UUID

import inngest

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.db.models import CriterionResult
from h_arcane.evaluation.context import EvaluationData, EvaluationRunner
from h_arcane.inngest.client import inngest_client
from h_arcane.inngest.events import CriterionEvaluationEvent


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

    This is an Inngest function that provides tracing for criterion evaluation.
    Delegates to rule.evaluate(runner) for the actual evaluation logic.
    """
    event_data = CriterionEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(event_data.run_id)

    # Build evaluation data
    max_score = event_data.rule.weight * event_data.stage.max_points
    data = EvaluationData(
        run_id=run_id,
        task_input=event_data.task_input,
        agent_reasoning=event_data.agent_reasoning,
        agent_outputs=event_data.agent_outputs,
        stage_idx=event_data.stage_idx,
        stage_name=event_data.stage.name,
        rule_idx=event_data.rule_idx,
        max_score=max_score,
    )

    # Create sandbox manager and runner with Inngest context for step tracing
    sandbox_manager = SandboxManager()
    runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=ctx)

    # Evaluate rule - granular steps are inside rule.evaluate()
    result = await event_data.rule.evaluate(runner)

    # Cleanup sandbox if we created one
    async def cleanup() -> dict:
        await runner.cleanup()
        return {"cleaned_up": True}

    await ctx.step.run("cleanup", cleanup)

    return result
