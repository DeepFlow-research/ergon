"""
Strongly-typed event contracts for task and workflow lifecycle.

These events are used with Inngest for orchestrating task execution.
Each contract defines both the event name and payload schema.

Usage:
    # Sending an event:
    await inngest_client.send(
        inngest.Event(
            name=TaskReadyEvent.name,
            data=TaskReadyEvent(run_id=..., task_id=...).model_dump(),
        )
    )

    # Receiving an event (in Inngest function):
    event = TaskReadyEvent(**ctx.event.data)
"""

from typing import ClassVar

from h_arcane.core._internal.events.base import InngestEventContract


# =============================================================================
# Task Lifecycle Events
# =============================================================================


class TaskReadyEvent(InngestEventContract):
    """
    Emitted when a task's dependencies are satisfied and it's ready to execute.

    Triggers: task_execute Inngest function
    """

    name: ClassVar[str] = "task/ready"

    run_id: str
    experiment_id: str
    task_id: str


class TaskStartedEvent(InngestEventContract):
    """
    Emitted when task execution begins.

    For observability/logging - not currently used as a trigger.
    """

    name: ClassVar[str] = "task/started"

    run_id: str
    experiment_id: str
    task_id: str
    execution_id: str


class TaskCompletedEvent(InngestEventContract):
    """
    Emitted when a task completes successfully.

    Triggers: task_propagate Inngest function
    """

    name: ClassVar[str] = "task/completed"

    run_id: str
    experiment_id: str
    task_id: str
    execution_id: str


class TaskFailedEvent(InngestEventContract):
    """
    Emitted when a task fails.

    Triggers: task_propagate (to check if workflow should fail)
    """

    name: ClassVar[str] = "task/failed"

    run_id: str
    experiment_id: str
    task_id: str
    execution_id: str
    error: str


# =============================================================================
# Workflow Lifecycle Events
# =============================================================================


class WorkflowStartedEvent(InngestEventContract):
    """
    Emitted to start workflow execution.

    Triggers: workflow_start Inngest function
    """

    name: ClassVar[str] = "workflow/started"

    run_id: str
    experiment_id: str


class WorkflowCompletedEvent(InngestEventContract):
    """
    Emitted when all tasks in a workflow complete successfully.

    Triggers: workflow_complete Inngest function
    """

    name: ClassVar[str] = "workflow/completed"

    run_id: str
    experiment_id: str


class WorkflowFailedEvent(InngestEventContract):
    """
    Emitted when a workflow fails (unrecoverable error or task failure).

    Triggers: workflow_failed Inngest function
    """

    name: ClassVar[str] = "workflow/failed"

    run_id: str
    experiment_id: str
    error: str


