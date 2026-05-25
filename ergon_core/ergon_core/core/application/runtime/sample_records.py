"""Sample creation, dispatch, and cancellation via Inngest."""

import logging
from uuid import UUID

import inngest
from ergon_core.core.application.experiments.models import DefinitionHandle
from ergon_core.core.application.events import SampleCancelledEvent, SampleCleanupEvent
from ergon_core.core.application.samples.events import SampleRuntimeEventAppender
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.persistence.samples.models import SampleStatusEventRow
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TERMINAL_SAMPLE_STATUSES, SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from sqlmodel import select
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.shared.settings import settings
from ergon_core.core.shared.utils import utcnow

logger = logging.getLogger(__name__)


def _checkpoint_metadata() -> JsonObject:
    """Checkpoint context for ``SampleRecord.summary_json`` (eval watcher / checkpoint subprocess).

    Values come from ``Settings`` (``.env`` + process env), including ``ERGON_CHECKPOINT_*``
    set by the eval runner when spawning evaluation.
    """
    if settings.checkpoint_step is None:
        return {}
    return {
        "checkpoint_step": settings.checkpoint_step,
        "checkpoint_path": settings.checkpoint_path,
    }


def create_definition_backed_sample(  # slopcop: ignore[max-function-params] -- service boundary mirrors SampleRecord provenance fields
    definition: DefinitionHandle,
    *,
    definition_id: UUID,
    instance_key: str,
    worker_team_json: JsonObject,
    evaluator_slug: str | None = None,
    model_target: str | None = None,
    sandbox_slug: str | None = None,
    dependency_extras_json: JsonObject | None = None,
    assignment_json: JsonObject | None = None,
    seed: int | None = None,
    experiment: str | None = None,
) -> SampleRecord:
    with get_session() as session:
        sample = SampleRecord(
            definition_id=definition_id,
            benchmark_type=definition.benchmark_type,
            instance_key=instance_key,
            worker_team_json=worker_team_json,
            evaluator_slug=evaluator_slug,
            model_target=model_target,
            sandbox_slug=sandbox_slug,
            dependency_extras_json=dependency_extras_json or {},
            assignment_json=assignment_json or {},
            seed=seed,
            experiment=experiment,
            status=SampleStatus.PENDING,
            created_at=utcnow(),
            summary_json=_checkpoint_metadata(),
        )
        session.add(sample)
        session.commit()
        session.refresh(sample)
        return sample


def cancel_sample(sample_id: UUID) -> SampleRecord:
    """Cancel a sample: mark CANCELLED in PG, kill Inngest functions, trigger cleanup."""
    with get_session() as session:
        sample = session.get(SampleRecord, sample_id)
        if sample is None:
            raise ValueError(f"Sample {sample_id} not found")
        if sample.status in TERMINAL_SAMPLE_STATUSES:
            raise ValueError(f"Sample {sample_id} is already in terminal state: {sample.status}")

        sample.status = SampleStatus.CANCELLED
        sample.completed_at = utcnow()
        session.add(sample)
        SampleRuntimeEventAppender(session).append_status_event(
            SampleStatusEventRow(
                sample_id=sample_id,
                event_type="sample.status_changed",
                status=SampleStatus.CANCELLED,
                actor="user:cancel_sample",
                event_timestamp=sample.completed_at,
            )
        )
        session.commit()
        session.refresh(sample)

    inngest_client.send_sync(
        inngest.Event(
            name=SampleCancelledEvent.name,
            data=SampleCancelledEvent(sample_id=sample_id).model_dump(mode="json"),
        )
    )

    inngest_client.send_sync(
        inngest.Event(
            name=SampleCleanupEvent.name,
            data=SampleCleanupEvent(
                sample_id=sample_id,
                status="cancelled",
            ).model_dump(mode="json"),
        )
    )

    logger.info("Cancelled sample %s and dispatched cleanup", sample_id)
    return sample


def latest_sample_for_definition(definition_id: UUID) -> SampleRecord | None:
    """Most-recent ``SampleRecord`` for a given definition, or None."""
    with get_session() as session:
        stmt = (
            select(SampleRecord)
            .where(SampleRecord.definition_id == definition_id)
            .order_by(SampleRecord.created_at.desc())
            .limit(1)
        )
        return session.exec(stmt).first()


create_run = create_definition_backed_sample
cancel_run = cancel_sample
latest_run_for_definition = latest_sample_for_definition
