"""Inngest functions for the infrastructure domain.

These functions handle infrastructure concerns:
- run_cleanup: Clean up sandbox after completion/failure
"""

from uuid import UUID

import inngest

from h_arcane.core.db.models import RunStatus
from h_arcane.core.db.queries import queries
from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.infrastructure.sandbox import BaseSandboxManager


@inngest_client.create_function(
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event="run/cleanup"),
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

    async def terminate_sandbox():
        run = queries.runs.get(run_id)
        if not run:
            return {
                "success": False,
                "run_id": str(run_id),
                "error": "Run not found",
            }

        if not run.e2b_sandbox_id:
            return {
                "success": True,
                "run_id": str(run_id),
                "sandbox_terminated": False,
                "message": "No sandbox ID stored - sandbox may not have been created",
            }

        terminated = await BaseSandboxManager.terminate_by_sandbox_id(run.e2b_sandbox_id)

        updated_run = run.model_copy(update={"e2b_sandbox_id": None})
        queries.runs.update(updated_run)

        return {
            "success": True,
            "run_id": str(run_id),
            "sandbox_terminated": terminated,
            "sandbox_id": run.e2b_sandbox_id,
        }

    terminate_result = await ctx.step.run("terminate-sandbox", terminate_sandbox)

    async def verify_run_status():
        run = queries.runs.get(run_id)
        if not run:
            return {"error": f"Run {run_id} not found"}

        expected_status = RunStatus.COMPLETED if status == "completed" else RunStatus.FAILED
        if run.status != expected_status:
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
