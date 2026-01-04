"""Run cleanup Inngest function."""

from uuid import UUID

import inngest

from h_arcane.core.db.models import RunStatus
from h_arcane.core.db.queries import queries
from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.infrastructure.sandbox import BaseSandboxManager


@inngest_client.create_function(
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event="run/cleanup"),
    retries=0,  # Retry cleanup if it fails
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
    # Parse event data
    event_data_dict = ctx.event.data
    run_id_str = str(event_data_dict.get("run_id", ""))
    status_str = str(event_data_dict.get("status", "failed"))
    error_message = (
        str(event_data_dict.get("error_message", ""))
        if event_data_dict.get("error_message")
        else None
    )

    run_id = UUID(run_id_str)
    status = status_str

    # Terminate sandbox using stored sandbox_id (works across process boundaries)
    async def terminate_sandbox():
        # Get the run to find the E2B sandbox_id
        run = queries.runs.get(run_id)
        if not run:
            return {
                "success": False,
                "run_id": str(run_id),
                "error": "Run not found",
            }

        if not run.e2b_sandbox_id:
            # No sandbox ID stored - sandbox may never have been created
            return {
                "success": True,
                "run_id": str(run_id),
                "sandbox_terminated": False,
                "message": "No sandbox ID stored - sandbox may not have been created",
            }

        # Use the static method to terminate by sandbox_id
        # This works across process boundaries since we use the E2B API directly
        terminated = await BaseSandboxManager.terminate_by_sandbox_id(run.e2b_sandbox_id)

        # Clear the sandbox_id from the run to prevent duplicate cleanup attempts
        updated_run = run.model_copy(update={"e2b_sandbox_id": None})
        queries.runs.update(updated_run)

        return {
            "success": True,
            "run_id": str(run_id),
            "sandbox_terminated": terminated,
            "sandbox_id": run.e2b_sandbox_id,
        }

    terminate_result = await ctx.step.run("terminate-sandbox", terminate_sandbox)

    # Verify run status is set correctly (idempotent check)
    async def verify_run_status():
        run = queries.runs.get(run_id)
        if not run:
            return {"error": f"Run {run_id} not found"}

        expected_status = RunStatus.COMPLETED if status == "completed" else RunStatus.FAILED
        if run.status != expected_status:
            # Update status if it doesn't match (shouldn't happen, but be safe)
            updated = run.model_copy(
                update={
                    "status": expected_status,
                    "error_message": error_message if status == "failed" else None,
                }
            )
            queries.runs.update(updated)
            return {
                "status_updated": True,
                "old_status": run.status.value,
                "new_status": expected_status.value,
            }
        return {
            "status_verified": True,
            "status": run.status.value,
        }

    status_result = await ctx.step.run("verify-run-status", verify_run_status)

    return {
        "run_id": str(run_id),
        "status": status,
        "sandbox_cleanup": terminate_result,
        "status_verification": status_result,
    }
