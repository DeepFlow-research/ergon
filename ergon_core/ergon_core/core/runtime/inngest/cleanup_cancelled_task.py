"""Inngest function: clean up resources for a cancelled task.

Two durable steps:
1. update-db-rows — mark execution CANCELLED (idempotent)
2. release-sandbox — stub (pending sandbox management module)
"""

import logging

import inngest

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
        "cleanup-cancelled node_id=%s execution_id=%s cause=%s",
        payload.node_id,
        payload.execution_id,
        payload.cause,
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
        from ergon_core.core.persistence.shared.db import get_session

        with get_session() as session:
            result = svc.cleanup(
                session,
                run_id=payload.run_id,
                node_id=payload.node_id,
                execution_id=payload.execution_id,
            )
        return result.model_dump(mode="json")

    return await ctx.step.run("update-db-rows", _update_db_rows)
