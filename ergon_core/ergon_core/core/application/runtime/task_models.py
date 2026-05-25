"""Task-domain request and response models."""

from uuid import UUID

from ergon_core.core.application.events import TaskCancelledEvent
from ergon_core.core.application.runtime.status import NodeStatus
from ergon_core.core.persistence.shared.types import NodeId, RunId
from pydantic import BaseModel, Field


# ── cancel_task ───────────────────────────────────────────────────────────


class CancelTaskCommand(BaseModel):
    """Command to cancel a subtask."""

    sample_id: RunId
    task_id: NodeId

    model_config = {"frozen": True}


class CancelTaskResult(BaseModel):
    """Result of cancelling a subtask."""

    task_id: NodeId
    old_status: str
    cascaded_count: int

    model_config = {"frozen": True}


# ── refine_task ───────────────────────────────────────────────────────────


class RefineTaskCommand(BaseModel):
    """Command to update description on a pending sub-task."""

    sample_id: RunId
    task_id: NodeId
    new_description: str = Field(min_length=1)

    model_config = {"frozen": True}


class RefineTaskResult(BaseModel):
    """Result of refining a subtask description."""

    task_id: NodeId
    old_description: str
    new_description: str

    model_config = {"frozen": True}


# ── restart_task ──────────────────────────────────────────────────────────


class RestartTaskCommand(BaseModel):
    """Command to reset a terminal subtask back to PENDING and re-queue it.

    Pairs with ``refine_task`` for the edit-then-rerun flow: the manager
    calls ``refine_task`` first to update the description, then
    ``restart_task`` to put the node back in the scheduling queue.
    """

    sample_id: RunId
    task_id: NodeId

    model_config = {"frozen": True}


class RestartTaskResult(BaseModel):
    """Result of restarting a subtask node.

    ``invalidated_task_ids`` lists any downstream targets that were
    cancelled because their input became stale (e.g. a COMPLETED
    downstream node whose upstream source is being re-run).
    """

    task_id: NodeId
    old_status: str
    invalidated_task_ids: list[NodeId] = Field(default_factory=list)

    model_config = {"frozen": True}


class CancelOrphansResult(BaseModel):
    """Result of cascade-cancelling non-terminal children of a parent node."""

    parent_task_id: NodeId
    cancelled_task_ids: list[NodeId]
    events_to_emit: list[TaskCancelledEvent]

    model_config = {"frozen": True}


class SubtaskInfo(BaseModel):
    """A snapshot of one subtask suitable for the manager to reason over."""

    task_id: NodeId
    task_slug: str
    description: str
    status: NodeStatus
    depends_on: list[NodeId]
    output: str | None
    error: str | None

    model_config = {"frozen": True}


class CleanupResult(BaseModel):
    """Result of cleaning up a cancelled task execution."""

    sample_id: RunId
    task_id: NodeId
    execution_id: UUID | None
    sandbox_id: str | None = None
    sandbox_released: bool
    execution_row_updated: bool

    model_config = {"frozen": True}
