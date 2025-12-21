"""Run cleanup Inngest function."""

from uuid import UUID

import inngest

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.db.models import RunStatus
from h_arcane.db.queries import queries
from h_arcane.inngest.client import inngest_client


@inngest_client.create_function(  # type: ignore[misc]
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event="run/cleanup"),
    retries=2,  # Retry cleanup if it fails
    concurrency=[inngest.Concurrency(limit=50, scope="fn")],
)
async def run_cleanup(
    ctx: inngest.Context,
) -> dict:
    """
    Cleanup function for completed or failed runs.

    Handles:
    - Terminating sandbox for the run_id
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

    # Terminate sandbox (idempotent - safe to call multiple times)
    async def terminate_sandbox():
        try:
            await SandboxManager().terminate(run_id)
            return {
                "success": True,
                "run_id": str(run_id),
                "sandbox_terminated": True,
            }
        except Exception as e:
            # Log but don't fail - sandbox might already be terminated
            error_str = str(e)
            if "not created" in error_str.lower() or "not found" in error_str.lower():
                # Sandbox already terminated or never existed - this is fine
                return {
                    "success": True,
                    "run_id": str(run_id),
                    "sandbox_terminated": False,
                    "message": "Sandbox already terminated or never existed",
                }
            # Other error - log but continue
            print(f"Warning: Error terminating sandbox for run_id={run_id}: {e}")
            return {
                "success": False,
                "run_id": str(run_id),
                "error": error_str,
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
