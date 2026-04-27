"""Run creation, dispatch, and cancellation via Inngest."""

import logging
from uuid import UUID

import inngest
from ergon_core.api.handles import PersistedExperimentDefinition
from ergon_core.api.json_types import JsonObject
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TERMINAL_RUN_STATUSES, RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.events.infrastructure_events import (
    RunCancelledEvent,
    RunCleanupEvent,
)
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.settings import settings
from ergon_core.core.utils import utcnow

logger = logging.getLogger(__name__)


def _checkpoint_metadata() -> JsonObject:
    """Checkpoint context for ``RunRecord.summary_json`` (eval watcher / checkpoint subprocess).

    Values come from ``Settings`` (``.env`` + process env), including ``ERGON_CHECKPOINT_*``
    set by the eval runner when spawning evaluation.
    """
    if settings.checkpoint_step is None:
        return {}
    return {
        "checkpoint_step": settings.checkpoint_step,
        "checkpoint_path": settings.checkpoint_path,
    }


def create_run(  # slopcop: ignore[max-function-params] -- service boundary mirrors RunRecord provenance fields
    definition: PersistedExperimentDefinition,
    *,
    experiment_id: UUID,
    workflow_definition_id: UUID,
    instance_key: str,
    worker_team_json: JsonObject,
    evaluator_slug: str | None = None,
    model_target: str | None = None,
    assignment_json: JsonObject | None = None,
    seed: int | None = None,
) -> RunRecord:
    with get_session() as session:
        run = RunRecord(
            experiment_id=experiment_id,
            workflow_definition_id=workflow_definition_id,
            benchmark_type=definition.benchmark_type,
            instance_key=instance_key,
            worker_team_json=worker_team_json,
            evaluator_slug=evaluator_slug,
            model_target=model_target,
            assignment_json=assignment_json or {},
            seed=seed,
            status=RunStatus.PENDING,
            created_at=utcnow(),
            summary_json=_checkpoint_metadata(),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run


def cancel_run(run_id: UUID) -> RunRecord:
    """Cancel a run: mark CANCELLED in PG, kill Inngest functions, trigger cleanup."""
    with get_session() as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        if run.status in TERMINAL_RUN_STATUSES:
            raise ValueError(f"Run {run_id} is already in terminal state: {run.status}")

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
