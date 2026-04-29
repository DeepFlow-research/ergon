"""Inngest function: clean up resources for a cancelled task.

Two durable steps:
1. update-db-rows — mark execution CANCELLED (idempotent)
2. release-sandbox — routed through the sandbox lifecycle provider when an
   execution has an associated sandbox.
"""

import logging

from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.events.task_events import TaskCancelledEvent
from ergon_core.core.application.tasks.models import CleanupResult
from ergon_core.core.application.tasks.cleanup import TaskCleanupService
from typing import Any

logger = logging.getLogger(__name__)


async def run_cleanup_cancelled_task_job(ctx: Any, payload: TaskCancelledEvent) -> JsonObject:
    """Clean up a single cancelled task's resources."""
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

    def _update_db_rows() -> JsonObject:
        with get_session() as session:
            result = svc.cleanup(
                session,
                run_id=payload.run_id,
                node_id=payload.node_id,
                execution_id=payload.execution_id,
            )
        return result.model_dump(mode="json")

    cleanup_result = await ctx.step.run("update-db-rows", _update_db_rows)

    await get_dashboard_emitter().task_cancelled(payload)

    return cleanup_result
