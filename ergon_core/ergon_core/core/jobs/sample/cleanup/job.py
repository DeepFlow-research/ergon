"""Inngest function: sample cleanup (sandbox teardown).

Terminates sandbox after sample completion/failure and ensures sample status is correct.
"""

import logging
from functools import partial
from uuid import UUID
from sqlmodel import Session, select

from ergon_core.core.application.runtime.task_management import TaskManagementService
from ergon_core.core.application.runtime.task_cleanup import TaskCleanupService
from ergon_core.core.application.runtime.task_models import CancelTaskCommand
from ergon_core.core.application.runtime.task_errors import TaskAlreadyTerminalError
from ergon_core.core.application.runtime.status import TERMINAL_STATUSES
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import SampleId, NodeId
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleTaskAttempt,
    SandboxEvent,
)
from ergon_core.core.infrastructure.inngest.errors import ConfigurationError, DataIntegrityError
from ergon_core.core.jobs.sandbox._lifecycle import terminate_external_sandbox
from .contract import SampleCleanupEvent, SampleCleanupResult
from typing import Any

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[str, SampleStatus] = {
    "completed": SampleStatus.COMPLETED,
    "failed": SampleStatus.FAILED,
    "cancelled": SampleStatus.CANCELLED,
}


async def run_sample_cleanup_job(ctx: Any, payload: SampleCleanupEvent) -> SampleCleanupResult:
    """Cleanup: terminate sandbox, ensure sample status is correct."""
    sample_id = payload.sample_id
    status = payload.status
    error_message = payload.error_message

    logger.info("sample-cleanup sample_id=%s status=%s", sample_id, status)

    return await ctx.step.run(
        "cleanup-sample",
        partial(_cleanup_sample, sample_id, status, error_message),
        output_type=SampleCleanupResult,
    )


async def _cleanup_sample(
    sample_id: UUID, status: str, error_message: str | None
) -> SampleCleanupResult:
    """Terminate sandbox and update sample status."""
    expected = _STATUS_MAP.get(status)
    if expected is None:
        raise ConfigurationError(
            f"Unknown cleanup status: {status!r}",
            sample_id=sample_id,
        )

    session = get_session()
    try:
        run = session.get(SampleRecord, sample_id)
        if run is None:
            raise DataIntegrityError("SampleRecord", sample_id)

        sandbox_id = run.parsed_summary().get("sandbox_id")
        sandbox_ids = {sandbox_id} if isinstance(sandbox_id, str) else set()
        if status == "cancelled":
            sandbox_ids.update(await _cancel_sample_work(session, sample_id))
        terminations = [await terminate_external_sandbox(key) for key in sorted(sandbox_ids)]
        sandbox_terminated = bool(terminations) and all(r.terminated for r in terminations)

        if sandbox_id is not None and not isinstance(sandbox_id, str):
            logger.warning(
                "sample-cleanup sample_id=%s: sandbox_id has unexpected type %s, skipping termination",
                sample_id,
                type(sandbox_id).__name__,
            )

        if run.status != expected:
            run.status = expected
            if status == "failed" and error_message:
                run.error_message = error_message

        session.add(run)
        session.commit()
    finally:
        session.close()

    return SampleCleanupResult(
        sample_id=sample_id,
        status=status,
        sandbox_terminated=sandbox_terminated,
        sandbox_id=sandbox_id if isinstance(sandbox_id, str) else None,
        sandbox_ids=tuple(sorted(sandbox_ids)),
    )


async def _cancel_sample_work(session: Session, sample_id: UUID) -> set[str]:
    """Finish cancellation through the existing task and cleanup owners.

    Sample cancellation stops orchestration handlers, including task cleanup
    already in flight. This surviving sample cleanup must cover every attempt,
    not just the historical sample-summary sandbox pointer.
    """
    management = TaskManagementService()
    for node in session.exec(
        select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
    ).all():
        if node.status not in TERMINAL_STATUSES:
            try:
                await management.cancel_task(
                    session,
                    CancelTaskCommand(sample_id=SampleId(sample_id), task_id=NodeId(node.task_id)),
                )
            except TaskAlreadyTerminalError:
                pass  # A native cascade won the same cancellation race.
    cleanup = TaskCleanupService()
    sandbox_ids = set()
    for attempt in session.exec(
        select(SampleTaskAttempt).where(SampleTaskAttempt.sample_id == sample_id)
    ).all():
        result = cleanup.cleanup(
            session, sample_id=sample_id, task_id=attempt.task_id, execution_id=attempt.id
        )
        if result.sandbox_id:
            sandbox_ids.add(result.sandbox_id)
    sandbox_ids.update(
        session.exec(
            select(SandboxEvent.sandbox_id).where(
                SandboxEvent.sample_id == sample_id, SandboxEvent.kind == "sandbox_created"
            )
        ).all()
    )
    return sandbox_ids
