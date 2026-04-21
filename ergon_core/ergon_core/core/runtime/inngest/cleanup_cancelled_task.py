"""Inngest function: clean up resources for a cancelled task.

Two durable steps:
1. update-db-rows — mark execution CANCELLED (idempotent)
2. release-sandbox — close the E2B sandbox if sandbox_id is present
"""

import logging

import inngest

from ergon_builtins.registry import SANDBOX_MANAGERS
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.runtime.events.task_events import TaskCancelledEvent
from ergon_core.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from ergon_core.core.runtime.services.task_cleanup_dto import CleanupResult
from ergon_core.core.runtime.services.task_cleanup_service import TaskCleanupService

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="cleanup-cancelled-task",
    trigger=inngest.TriggerEvent(event="task/cancelled"),
    cancel=RUN_CANCEL,
    retries=3,
)
async def cleanup_cancelled_task_fn(ctx: inngest.Context) -> dict:
    """Clean up a single cancelled task's resources."""
    payload = TaskCancelledEvent.model_validate(ctx.event.data)
    logger.info(
        "cleanup-cancelled node_id=%s execution_id=%s cause=%s sandbox_id=%s",
        payload.node_id,
        payload.execution_id,
        payload.cause,
        payload.sandbox_id,
    )

    if payload.execution_id is None:
        return CleanupResult(
            run_id=payload.run_id,
            node_id=payload.node_id,
            execution_id=None,
            sandbox_released=False,
            execution_row_updated=False,
        ).model_dump(mode="json")

    svc = TaskCleanupService()

    def _update_db_rows() -> dict:
        # reason: deferred to avoid circular import at module level
        from ergon_core.core.persistence.shared.db import get_session

        with get_session() as session:
            result = svc.cleanup(
                session,
                run_id=payload.run_id,
                node_id=payload.node_id,
                execution_id=payload.execution_id,
            )
        return result.model_dump(mode="json")

    db_result_raw = await ctx.step.run("update-db-rows", _update_db_rows)

    async def _release_sandbox() -> dict:
        if payload.sandbox_id is None or payload.benchmark_slug is None:
            logger.info(
                "release-sandbox skipped: no sandbox_id or benchmark_slug for node_id=%s",
                payload.node_id,
            )
            return {"sandbox_released": False, "reason": "no_payload"}

        mgr_cls = SANDBOX_MANAGERS.get(payload.benchmark_slug)
        if mgr_cls is None:
            logger.warning(
                "release-sandbox: no manager for benchmark_slug=%s node_id=%s",
                payload.benchmark_slug,
                payload.node_id,
            )
            return {"sandbox_released": False, "reason": "unknown_slug"}

        released = await BaseSandboxManager.terminate_by_sandbox_id(payload.sandbox_id)
        logger.info(
            "release-sandbox sandbox_id=%s benchmark_slug=%s released=%s",
            payload.sandbox_id,
            payload.benchmark_slug,
            released,
        )
        return {"sandbox_released": released, "reason": "terminated"}

    sandbox_result = await ctx.step.run("release-sandbox", _release_sandbox)

    await dashboard_emitter.task_cancelled(payload)

    # Merge results for the function return value.
    db_result = CleanupResult.model_validate(db_result_raw)
    sandbox_released: bool = sandbox_result.get("sandbox_released") or False
    return CleanupResult(
        run_id=db_result.run_id,
        node_id=db_result.node_id,
        execution_id=db_result.execution_id,
        sandbox_released=sandbox_released,
        execution_row_updated=db_result.execution_row_updated,
    ).model_dump(mode="json")
