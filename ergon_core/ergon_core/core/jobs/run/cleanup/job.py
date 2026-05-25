"""Inngest function: run cleanup (sandbox teardown).

Terminates sandbox after run completion/failure and ensures run status is correct.
"""

import logging
from functools import partial
from uuid import UUID

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
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
    """Cleanup: terminate sandbox, ensure run status is correct."""
    sample_id = payload.sample_id
    status = payload.status
    error_message = payload.error_message

    logger.info("run-cleanup sample_id=%s status=%s", sample_id, status)

    return await ctx.step.run(
        "cleanup-run",
        partial(_cleanup_run, sample_id, status, error_message),
        output_type=SampleCleanupResult,
    )


async def _cleanup_run(
    sample_id: UUID, status: str, error_message: str | None
) -> SampleCleanupResult:
    """Terminate sandbox and update run status."""
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
        sandbox_result = await terminate_external_sandbox(
            sandbox_id if isinstance(sandbox_id, str) else None
        )
        sandbox_terminated = sandbox_result.terminated

        if sandbox_id is not None and not isinstance(sandbox_id, str):
            logger.warning(
                "run-cleanup sample_id=%s: sandbox_id has unexpected type %s, skipping termination",
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
    )
