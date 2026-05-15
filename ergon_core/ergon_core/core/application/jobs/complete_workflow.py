"""Inngest function: workflow completion finalization."""

import logging
from datetime import UTC, datetime

from ergon_core.core.infrastructure.dashboard import emit_cohort_updated_for_run
from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord, RunRecord
from ergon_core.core.application.events.infrastructure_events import RunCleanupEvent
from ergon_core.core.application.events.task_events import WorkflowCompletedEvent
from ergon_core.core.infrastructure.inngest.client import InngestEvent, inngest_client
from ergon_core.core.application.jobs.models import WorkflowCompleteResult
from ergon_core.core.application.workflows.orchestration import FinalizeWorkflowCommand
from ergon_core.core.application.workflows.service import WorkflowService
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_complete_context,
    workflow_root_context,
)

logger = logging.getLogger(__name__)


async def run_complete_workflow_job(payload: WorkflowCompletedEvent) -> WorkflowCompleteResult:
    logger.info("workflow-complete run_id=%s", payload.run_id)
    span_start = datetime.now(UTC)

    svc = WorkflowService()
    finalized = svc.finalize(
        FinalizeWorkflowCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
        )
    )

    await emit_cohort_updated_for_run(payload.run_id)

    with get_session() as _session:
        _run = _session.get(RunRecord, payload.run_id)
        _duration = (
            (_run.completed_at - _run.started_at).total_seconds()
            if _run and _run.started_at and _run.completed_at
            else 0.0
        )
    await get_dashboard_emitter().workflow_completed(
        run_id=payload.run_id,
        status="completed",
        duration_seconds=_duration,
        final_score=finalized.final_score,
    )

    await inngest_client.send(
        InngestEvent(
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

    sink = get_trace_sink()
    sink.emit_span(
        CompletedSpan(
            name="workflow.complete",
            context=workflow_complete_context(payload.run_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(payload.run_id),
                "definition_id": str(payload.definition_id),
                "final_score": finalized.final_score,
                "normalized_score": finalized.normalized_score,
                "evaluators_count": finalized.evaluators_count,
            },
        )
    )

    with get_session() as session:
        run = session.get(RunRecord, payload.run_id)
        experiment = session.get(BenchmarkDefinitionRecord, run.experiment_id) if run else None
        if run and run.started_at and run.completed_at:
            sink.emit_span(
                CompletedSpan(
                    name="workflow.execute",
                    context=workflow_root_context(payload.run_id),
                    start_time=run.started_at,
                    end_time=run.completed_at,
                    attributes={
                        "run_id": str(payload.run_id),
                        "definition_id": str(payload.definition_id),
                        "cohort_id": str(experiment.cohort_id)
                        if experiment and experiment.cohort_id
                        else "",
                        "status": run.status,
                        "final_score": finalized.final_score,
                        "normalized_score": finalized.normalized_score,
                    },
                )
            )

    logger.info(
        "workflow-complete done: score=%s normalized=%s evaluators=%d",
        result.final_score,
        result.normalized_score,
        result.evaluators_count,
    )
    return result
