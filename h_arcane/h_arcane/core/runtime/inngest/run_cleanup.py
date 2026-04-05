"""Inngest function: run cleanup (sandbox teardown).

Terminates sandbox after run completion/failure and ensures run status is correct.
"""

import logging
from functools import partial
from uuid import UUID

import inngest
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.shared.enums import RunStatus
from h_arcane.core.persistence.telemetry.models import RunRecord
from h_arcane.core.providers.sandbox.manager import BaseSandboxManager
from h_arcane.core.runtime.errors import ConfigurationError, DataIntegrityError
from h_arcane.core.runtime.events.infrastructure_events import RunCleanupEvent
from h_arcane.core.runtime.inngest_client import inngest_client
from h_arcane.core.runtime.services.inngest_function_results import RunCleanupResult

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[str, RunStatus] = {
    "completed": RunStatus.COMPLETED,
    "failed": RunStatus.FAILED,
    "cancelled": RunStatus.CANCELLED,
}


@inngest_client.create_function(
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event="run/cleanup"),
    retries=0,
    output_type=RunCleanupResult,
)
async def run_cleanup_fn(ctx: inngest.Context) -> RunCleanupResult:
    """Cleanup: terminate sandbox, ensure run status is correct."""
    payload = RunCleanupEvent(**ctx.event.data)
    run_id = payload.run_id
    status = payload.status
    error_message = payload.error_message

    logger.info("run-cleanup run_id=%s status=%s", run_id, status)

    return await ctx.step.run(
        "cleanup-run",
        partial(_cleanup_run, run_id, status, error_message),
        output_type=RunCleanupResult,
    )


async def _cleanup_run(
    run_id: UUID, status: str, error_message: str | None
) -> RunCleanupResult:
    """Terminate sandbox and update run status."""
    expected = _STATUS_MAP.get(status)
    if expected is None:
        raise ConfigurationError(
            f"Unknown cleanup status: {status!r}",
            run_id=run_id,
        )

    session = get_session()
    try:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise DataIntegrityError("RunRecord", run_id)

        sandbox_id = run.parsed_summary().get("sandbox_id")
        sandbox_terminated = False

        if sandbox_id and isinstance(sandbox_id, str):
            sandbox_terminated = (
                await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)
            )
        elif sandbox_id is not None:
            logger.warning(
                "run-cleanup run_id=%s: sandbox_id has unexpected type %s, skipping termination",
                run_id, type(sandbox_id).__name__,
            )

        if run.status != expected:
            run.status = expected
            if status == "failed" and error_message:
                run.error_message = error_message

        session.add(run)
        session.commit()
    finally:
        session.close()

    return RunCleanupResult(
        run_id=run_id,
        status=status,
        sandbox_terminated=sandbox_terminated,
        sandbox_id=sandbox_id if isinstance(sandbox_id, str) else None,
    )
