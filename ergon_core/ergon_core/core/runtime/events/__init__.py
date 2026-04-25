"""Inngest event contracts."""

from ergon_core.core.runtime.events.base import InngestEventContract
from ergon_core.core.runtime.events.infrastructure_events import RunCleanupEvent
from ergon_core.core.runtime.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
    TaskStartedEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
)

__all__ = [
    "InngestEventContract",
    "RunCleanupEvent",
    "TaskCompletedEvent",
    "TaskFailedEvent",
    "TaskReadyEvent",
    "TaskStartedEvent",
    "WorkflowCompletedEvent",
    "WorkflowFailedEvent",
    "WorkflowStartedEvent",
]
