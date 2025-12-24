"""Task run evaluator - delegates to rubric's compute_scores method."""

from uuid import UUID

import inngest

from h_arcane.core.db.models import TaskEvaluationResult
from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.evaluation.task_context import TaskEvaluationContext
from h_arcane.core.orchestration.events import TaskEvaluationEvent


@inngest_client.create_function(
    fn_id="evaluate-task-run",
    trigger=inngest.TriggerEvent(event="task/evaluate"),
    retries=2,
    concurrency=[inngest.Concurrency(limit=10, scope="fn")],
    output_type=TaskEvaluationResult,
)
async def evaluate_task_run(ctx: inngest.Context) -> TaskEvaluationResult:
    """
    Evaluate a task run by delegating to rubric.compute_scores().

    Pydantic handles all deserialization automatically via model_validate():
    - agent_outputs: list[Resource] auto-deserialized
    - rubric: AnyRubric auto-selects correct type via discriminator
    """
    event_data = TaskEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(event_data.run_id)

    # Build context - all fields already deserialized by Pydantic
    context = TaskEvaluationContext(
        run_id=run_id,
        task_input=event_data.task_input,
        agent_reasoning=event_data.agent_reasoning,
        agent_outputs=event_data.agent_outputs,
        rubric=event_data.rubric,
    )

    # Polymorphic dispatch - each rubric type implements its own scoring
    result = await event_data.rubric.compute_scores(context, ctx)

    return result
