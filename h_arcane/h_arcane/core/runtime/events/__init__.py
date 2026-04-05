"""Inngest event contracts."""

from h_arcane.core.runtime.events.base import InngestEventContract
from h_arcane.core.runtime.events.evaluation_events import (
    CriterionEvaluationEvent,
    TaskEvaluationEvent,
)
from h_arcane.core.runtime.events.infrastructure_events import RunCleanupEvent
from h_arcane.core.runtime.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
    TaskStartedEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
)

__all__ = [
    "CriterionEvaluationEvent",
    "InngestEventContract",
    "RunCleanupEvent",
    "TaskCompletedEvent",
    "TaskEvaluationEvent",
    "TaskFailedEvent",
    "TaskReadyEvent",
    "TaskStartedEvent",
    "WorkflowCompletedEvent",
    "WorkflowFailedEvent",
    "WorkflowStartedEvent",
]
