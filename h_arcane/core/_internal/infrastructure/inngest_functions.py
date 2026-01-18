"""Inngest functions for the infrastructure domain.

These functions handle infrastructure concerns:
- run_cleanup: Clean up sandbox after completion/failure
"""

from uuid import UUID

import inngest

from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.events import RunCleanupEvent
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.core._internal.infrastructure.step_outputs import (
    TerminateSandboxResult,
    VerifyRunStatusResult,
)


@inngest_client.create_function(
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event=RunCleanupEvent.name),
    retries=0,
    concurrency=[inngest.Concurrency(limit=50, scope="fn")],
)
async def run_cleanup(
    ctx: inngest.Context,
) -> dict:
    """
    Cleanup function for completed or failed runs.

    Handles:
    - Terminating sandbox using stored E2B sandbox_id (works across process boundaries)
    - Ensuring run status is correctly set (idempotent)
    - Logging cleanup results
    """
    payload = RunCleanupEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)
    status = payload.status
    error_message = payload.error_message

    async def terminate_sandbox() -> TerminateSandboxResult:
        run = queries.runs.get(run_id)
        if not run:
            return TerminateSandboxResult(
                success=False,
                run_id=str(run_id),
                error="Run not found",
            )

        if not run.e2b_sandbox_id:
            return TerminateSandboxResult(
                success=True,
                run_id=str(run_id),
                sandbox_terminated=False,
                message="No sandbox ID stored - sandbox may not have been created",
            )

        terminated = await BaseSandboxManager.terminate_by_sandbox_id(run.e2b_sandbox_id)

        updated_run = run.model_copy(update={"e2b_sandbox_id": None})
        queries.runs.update(updated_run)

        return TerminateSandboxResult(
            success=True,
            run_id=str(run_id),
            sandbox_terminated=terminated,
            sandbox_id=run.e2b_sandbox_id,
        )

    terminate_result = await ctx.step.run(
        "terminate-sandbox", terminate_sandbox, output_type=TerminateSandboxResult
    )
    terminate_result = terminate_result or TerminateSandboxResult(
        success=False, run_id=str(run_id), error="Step returned None"
    )

    async def verify_run_status() -> VerifyRunStatusResult:
        run = queries.runs.get(run_id)
        if not run:
            return VerifyRunStatusResult(error=f"Run {run_id} not found")

        expected_status = RunStatus.COMPLETED if status == "completed" else RunStatus.FAILED
        if run.status != expected_status:
            updated = run.model_copy(
                update={
                    "status": expected_status,
                    "error_message": error_message if status == "failed" else None,
                }
            )
            queries.runs.update(updated)
            return VerifyRunStatusResult(
                status_updated=True,
                old_status=run.status.value,
                new_status=expected_status.value,
            )
        return VerifyRunStatusResult(
            status_verified=True,
            status=run.status.value,
        )

    status_result = await ctx.step.run(
        "verify-run-status", verify_run_status, output_type=VerifyRunStatusResult
    )
    status_result = status_result or VerifyRunStatusResult(
        error="Step returned None"
    )

    return {
        "run_id": str(run_id),
        "status": status,
        "sandbox_cleanup": terminate_result.model_dump(),
        "status_verification": status_result.model_dump(),
    }
