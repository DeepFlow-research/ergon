"""Run cleanup Inngest function.

Cleans up sandbox after completion/failure.
"""

from uuid import UUID

import inngest

from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.events import RunCleanupEvent
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.results import RunCleanupResult
from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.core._internal.utils import require_not_none


@inngest_client.create_function(
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event=RunCleanupEvent.name),
    retries=0,
    concurrency=[inngest.Concurrency(limit=50, scope="fn")],
    output_type=RunCleanupResult,
)
async def run_cleanup(ctx: inngest.Context) -> RunCleanupResult:
    """
    Cleanup function for completed or failed runs.

    Handles:
    - Terminating sandbox using stored E2B sandbox_id
    - Ensuring run status is correctly set (idempotent)
    """
    payload = RunCleanupEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)
    status = payload.status
    error_message = payload.error_message

    # Combined: terminate sandbox + verify/update run status
    async def cleanup_run() -> RunCleanupResult:
        run = queries.runs.get(run_id)
        if not run:
            return RunCleanupResult(
                run_id=run_id,
                status=status,
                sandbox_terminated=False,
                error="Run not found",
            )

        sandbox_id = run.e2b_sandbox_id
        sandbox_terminated = False

        # Terminate sandbox if exists
        if sandbox_id:
            sandbox_terminated = await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)
            # Clear sandbox ID from run
            run = run.model_copy(update={"e2b_sandbox_id": None})

        # Verify/update run status
        expected_status = RunStatus.COMPLETED if status == "completed" else RunStatus.FAILED
        if run.status != expected_status:
            run = run.model_copy(
                update={
                    "status": expected_status,
                    "error_message": error_message if status == "failed" else run.error_message,
                }
            )

        # Single update with all changes
        queries.runs.update(run)

        return RunCleanupResult(
            run_id=run_id,
            status=status,
            sandbox_terminated=sandbox_terminated,
            sandbox_id=sandbox_id,
        )

    result = await ctx.step.run("cleanup-run", cleanup_run, output_type=RunCleanupResult)
    return require_not_none(result, "cleanup-run returned None")
