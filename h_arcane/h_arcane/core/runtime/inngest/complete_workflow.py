"""Inngest function: workflow completion finalization."""

import logging

import inngest
from h_arcane.core.runtime.events.infrastructure_events import RunCleanupEvent
from h_arcane.core.runtime.events.task_events import WorkflowCompletedEvent
from h_arcane.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from h_arcane.core.runtime.services.inngest_function_results import WorkflowCompleteResult
from h_arcane.core.runtime.services.orchestration_dto import FinalizeWorkflowCommand
from h_arcane.core.runtime.services.workflow_finalization_service import (
    WorkflowFinalizationService,
)

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="workflow-complete",
    trigger=inngest.TriggerEvent(event="workflow/completed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=WorkflowCompleteResult,
)
async def complete_workflow_fn(ctx: inngest.Context) -> WorkflowCompleteResult:
    payload = WorkflowCompletedEvent(**ctx.event.data)
    logger.info("workflow-complete run_id=%s", payload.run_id)

    svc = WorkflowFinalizationService()
    finalized = svc.finalize(
        FinalizeWorkflowCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
        )
    )

    await inngest_client.send(
        inngest.Event(
            name=RunCleanupEvent.name,
            data=RunCleanupEvent(
                run_id=payload.run_id,
                status="completed",
            ).model_dump(mode="json"),
        )
    )

    result = WorkflowCompleteResult(
        run_id=payload.run_id,
        status="completed",
        final_score=finalized.final_score,
        normalized_score=finalized.normalized_score,
        evaluators_count=finalized.evaluators_count,
    )
    logger.info(
        "workflow-complete done: score=%s normalized=%s evaluators=%d",
        result.final_score,
        result.normalized_score,
        result.evaluators_count,
    )
    return result
