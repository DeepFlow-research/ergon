"""Inngest event contracts."""

from ergon_core.core.application.events.base import InngestEventContract
from ergon_core.core.application.events.infrastructure_events import RunCleanupEvent
from ergon_core.core.application.events.task_events import (
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
