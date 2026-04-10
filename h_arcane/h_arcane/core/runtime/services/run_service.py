"""Run creation, dispatch, and cancellation via Inngest."""

import asyncio
import logging
from uuid import UUID

import inngest
from h_arcane.api.handles import ExperimentRunHandle, PersistedExperimentDefinition
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.shared.enums import TERMINAL_RUN_STATUSES, RunStatus
from h_arcane.core.persistence.telemetry.models import RunRecord
from h_arcane.core.runtime.events.infrastructure_events import (
    RunCancelledEvent,
    RunCleanupEvent,
)
from h_arcane.core.runtime.events.task_events import WorkflowStartedEvent
from h_arcane.core.runtime.inngest_client import inngest_client
from h_arcane.core.settings import settings
from h_arcane.core.utils import utcnow

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 1.0
_DEFAULT_TIMEOUT_S = 600.0


def _checkpoint_metadata() -> dict[str, object]:
    """Checkpoint context for ``RunRecord.summary_json`` (eval watcher / checkpoint subprocess).

    Values come from ``Settings`` (``.env`` + process env), including ``ARCANE_CHECKPOINT_*``
    set by the eval runner when spawning evaluation.
    """
    if settings.checkpoint_step is None:
        return {}
    return {
        "checkpoint_step": settings.checkpoint_step,
        "checkpoint_path": settings.checkpoint_path or "",
    }


def create_run(
    definition: PersistedExperimentDefinition,
    cohort_id: UUID | None = None,
) -> RunRecord:
    with get_session() as session:
        run = RunRecord(
            experiment_definition_id=definition.definition_id,
            cohort_id=cohort_id,
            status=RunStatus.PENDING,
            created_at=utcnow(),
            summary_json=_checkpoint_metadata(),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run


async def create_experiment_run(
    definition: PersistedExperimentDefinition,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> ExperimentRunHandle:
    run = create_run(definition)

    event = WorkflowStartedEvent(
        run_id=run.id,
        definition_id=definition.definition_id,
    )
    inngest_client.send_sync(
        inngest.Event(
            name=WorkflowStartedEvent.name,
            data=event.model_dump(mode="json"),
        )
    )

    logger.info("Dispatched workflow/started for run %s", run.id)

    elapsed = 0.0
    final_status = RunStatus.PENDING
    while elapsed < timeout_s:
        await asyncio.sleep(_POLL_INTERVAL_S)
        elapsed += _POLL_INTERVAL_S

        with get_session() as session:
            current = session.get(RunRecord, run.id)
            if current is None:
                raise RuntimeError(f"RunRecord {run.id} vanished during polling")
            final_status = current.status
            if final_status in TERMINAL_RUN_STATUSES:
                break

    if final_status not in TERMINAL_RUN_STATUSES:
        logger.warning("Run %s did not reach terminal state within %ss", run.id, timeout_s)

    return ExperimentRunHandle(
        run_id=run.id,
        definition_id=definition.definition_id,
        benchmark_type=definition.benchmark_type,
        status=final_status,
        worker_bindings=definition.worker_bindings,
        created_at=run.created_at,
        started_at=run.started_at,
        metadata=definition.metadata,
    )


def cancel_run(run_id: UUID) -> RunRecord:
    """Cancel a run: mark CANCELLED in PG, kill Inngest functions, trigger cleanup."""
    with get_session() as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        if run.status in TERMINAL_RUN_STATUSES:
            raise ValueError(
                f"Run {run_id} is already in terminal state: {run.status}"
            )

        run.status = RunStatus.CANCELLED
        run.completed_at = utcnow()
        session.add(run)
        session.commit()
        session.refresh(run)

    inngest_client.send_sync(
        inngest.Event(
            name=RunCancelledEvent.name,
            data=RunCancelledEvent(run_id=run_id).model_dump(mode="json"),
        )
    )

    inngest_client.send_sync(
        inngest.Event(
            name=RunCleanupEvent.name,
            data=RunCleanupEvent(
                run_id=run_id,
                status="cancelled",
            ).model_dump(mode="json"),
        )
    )

    logger.info("Cancelled run %s and dispatched cleanup", run_id)
    return run
