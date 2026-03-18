"""Task-level evaluation Inngest function.

This function evaluates a task run by delegating to rubric.compute_scores().
"""

from uuid import UUID

import inngest

from h_arcane.core._internal.db.models import TaskEvaluationResult, CriterionResult
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.evaluation.events import TaskEvaluationEvent
from h_arcane.core._internal.evaluation.schemas import TaskEvaluationContext
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client


@inngest_client.create_function(
    fn_id="evaluate-task-run",
    trigger=inngest.TriggerEvent(event=TaskEvaluationEvent.name),
    retries=0,
    concurrency=[inngest.Concurrency(limit=10, scope="fn")],
    output_type=TaskEvaluationResult,
)
async def evaluate_task_run(ctx: inngest.Context) -> TaskEvaluationResult:
    """
    Evaluate a task run by delegating to rubric.compute_scores().

    Pydantic handles all deserialization automatically via model_validate():
    - agent_outputs: list[Resource] auto-deserialized
    - rubric: AnyRubric auto-selects correct type via discriminator

    Persists:
    - CriterionResult records for each criterion evaluated
    - TaskEvaluationResult record with aggregate scores
    """
    payload = TaskEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)

    context = TaskEvaluationContext(
        run_id=run_id,
        task_input=payload.task_input,
        agent_reasoning=payload.agent_reasoning,
        agent_outputs=payload.agent_outputs,
        rubric=payload.rubric,
    )

    # Polymorphic dispatch - each rubric type implements its own scoring
    result = await payload.rubric.compute_scores(context, ctx)

    # Persist criterion results
    async def persist_criterion_results() -> int:
        for cr_dict in result.criterion_results:
            # Deserialize dict back to typed CriterionResult, ensuring run_id is set
            cr_dict["run_id"] = run_id
            cr = CriterionResult.model_validate(cr_dict)
            queries.criterion_results.create(cr)
        return len(result.criterion_results)

    await ctx.step.run("persist-criterion-results", persist_criterion_results)

    # Persist task evaluation result
    async def persist_task_evaluation_result() -> None:
        # Set the run_id on the result before persisting
        result.run_id = run_id
        queries.task_evaluation_results.create(result)

    await ctx.step.run("persist-task-evaluation-result", persist_task_evaluation_result)

    return result
