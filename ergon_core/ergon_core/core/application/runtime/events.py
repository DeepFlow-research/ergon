"""Runtime event dispatch ownership.

Runtime services call this module only after their database transaction has
committed. Keeping ready-event emission here prevents task management and run
lifecycle code from growing separate Inngest payload builders.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

import inngest

from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.application.events import TaskReadyEvent

logger = logging.getLogger(__name__)

TaskReadyDispatcher = Callable[[UUID, UUID], Awaitable[None]]


class RuntimeEventDispatcher:
    """Dispatches runtime-owned events without owning lifecycle decisions."""

    def __init__(self, task_ready_dispatcher: TaskReadyDispatcher | None = None) -> None:
        self._task_ready_dispatcher = task_ready_dispatcher

    async def dispatch_task_ready(
        self,
        *,
        sample_id: UUID,
        task_id: UUID,
    ) -> None:
        """Emit the canonical ``task/ready`` event for a committed task state."""
        if self._task_ready_dispatcher is not None:
            await self._task_ready_dispatcher(sample_id, task_id)
            logger.info("dispatch_task_ready: fired custom dispatcher for task %s", task_id)
            return

        event = TaskReadyEvent(
            sample_id=sample_id,
            task_id=task_id,
        )
        inngest_client.send_sync(
            inngest.Event(
                name=TaskReadyEvent.name,
                data=event.model_dump(mode="json"),
            )
        )
        logger.info("dispatch_task_ready: fired task/ready for task %s", task_id)
