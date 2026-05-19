"""Inngest function: clean up resources for a cancelled task.

Two durable steps:
1. update-db-rows — mark execution CANCELLED (idempotent)
2. release-sandbox — terminate the execution sandbox if one was acquired.
"""

import logging

from ergon_core.core.application.ports.dashboard import get_dashboard_event_publisher
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.events.task_events import TaskCancelledEvent
from ergon_core.core.application.tasks.models import CleanupResult
from ergon_core.core.application.tasks.cleanup import TaskCleanupService
from ergon_core.core.infrastructure.sandbox.lifecycle import terminate_external_sandbox
from ergon_core.core.shared.utils import utcnow
from ergon_core.core.views.dashboard_events.contracts import DashboardTaskStatusChangedEvent
from typing import Any

logger = logging.getLogger(__name__)


async def run_cleanup_cancelled_task_job(ctx: Any, payload: TaskCancelledEvent) -> JsonObject:
    """Clean up a single cancelled task's resources."""
    logger.info(
        "cleanup-cancelled task_id=%s execution_id=%s cause=%s",
        payload.task_id,
        payload.execution_id,
        payload.cause,
    )

    if payload.execution_id is None:
        return CleanupResult(
            run_id=payload.run_id,
            task_id=payload.task_id,
            execution_id=None,
            sandbox_id=None,
            sandbox_released=False,
            execution_row_updated=False,
        ).model_dump(mode="json")

    svc = TaskCleanupService()

    def _update_db_rows() -> JsonObject:
        with get_session() as session:
            result = svc.cleanup(
                session,
                run_id=payload.run_id,
                node_id=payload.task_id,
                execution_id=payload.execution_id,
            )
        return result.model_dump(mode="json")

    cleanup_result = await ctx.step.run("update-db-rows", _update_db_rows)
    result = CleanupResult.model_validate(cleanup_result)

    async def _release_sandbox() -> bool:
        termination = await terminate_external_sandbox(result.sandbox_id)
        return termination.terminated

    if result.sandbox_id is not None:
        sandbox_released = await ctx.step.run("release-sandbox", _release_sandbox)
        result = result.model_copy(update={"sandbox_released": sandbox_released})

    await get_dashboard_event_publisher().publish(
        DashboardTaskStatusChangedEvent(
            run_id=payload.run_id,
            task_id=payload.task_id,
            task_name="",
            parent_task_id=None,
            old_status=None,
            new_status="cancelled",
            triggered_by=f"cancel:{payload.cause}",
            timestamp=utcnow(),
            assigned_worker_id=None,
            assigned_worker_slug=None,
        )
    )

    return result.model_dump(mode="json")
