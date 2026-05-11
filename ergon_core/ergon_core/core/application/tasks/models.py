"""Task-domain request and response models."""

from uuid import UUID

from ergon_core.api import Task
from ergon_core.core.persistence.graph.status_conventions import NodeStatus
from ergon_core.core.persistence.shared.types import (
    AssignedWorkerSlug,
    NodeId,
    RunId,
    TaskSlug,
)
from ergon_core.core.application.events.task_events import TaskCancelledEvent
from pydantic import BaseModel, Field


class AddSubtaskCommand(BaseModel):
    """Create one subtask under a parent node.

    definition_id is NOT here — the service resolves it from run_id
    at dispatch time.
    """

    run_id: RunId
    parent_task_id: UUID
    task: Task
    depends_on: list[UUID] = Field(default_factory=list)

    model_config = {"frozen": True}


class AddSubtaskResult(BaseModel):
    """Result snapshot after creating a subtask node."""

    task_id: UUID
    task_slug: TaskSlug
    status: str

    model_config = {"frozen": True}


# ── plan_subtasks ──────────────────────────────────────────────────────────


class SubtaskSpec(BaseModel):
    """One entry in a plan_subtasks call."""

    task: Task
    depends_on: list[TaskSlug] = Field(default_factory=list)

    model_config = {"frozen": True}


class PlanSubtasksCommand(BaseModel):
    """Batch-create subtasks with local dependency references."""

    run_id: RunId
    parent_task_id: UUID
    subtasks: list[SubtaskSpec]

    model_config = {"frozen": True}


class PlanSubtasksResult(BaseModel):
    """Maps task_slug to created node_id plus identifies root tasks."""

    tasks: dict[TaskSlug, UUID]
    roots: list[TaskSlug]

    model_config = {"frozen": True}


# ── cancel_task ───────────────────────────────────────────────────────────


class CancelTaskCommand(BaseModel):
    """Command to cancel a subtask node."""

    run_id: RunId
    node_id: NodeId

    model_config = {"frozen": True}


class CancelTaskResult(BaseModel):
    """Result of cancelling a subtask node."""

    node_id: NodeId
    old_status: str
    cascaded_count: int

    model_config = {"frozen": True}


# ── refine_task ───────────────────────────────────────────────────────────


class RefineTaskCommand(BaseModel):
    """Command to update description on a pending sub-task."""

    run_id: RunId
    node_id: NodeId
    new_description: str = Field(min_length=1)

    model_config = {"frozen": True}


class RefineTaskResult(BaseModel):
    """Result of refining a subtask description."""

    node_id: NodeId
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

    run_id: RunId
    node_id: NodeId

    model_config = {"frozen": True}


class RestartTaskResult(BaseModel):
    """Result of restarting a subtask node.

    ``invalidated_node_ids`` lists any downstream targets that were
    cancelled because their input became stale (e.g. a COMPLETED
    downstream node whose upstream source is being re-run).
    """

    node_id: NodeId
    old_status: str
    invalidated_node_ids: list[NodeId] = Field(default_factory=list)

    model_config = {"frozen": True}


class CancelOrphansResult(BaseModel):
    """Result of cascade-cancelling non-terminal children of a parent node."""

    parent_node_id: NodeId
    cancelled_node_ids: list[NodeId]
    events_to_emit: list[TaskCancelledEvent]

    model_config = {"frozen": True}


class SubtaskInfo(BaseModel):
    """A snapshot of one subtask suitable for the manager to reason over."""

    task_id: UUID
    task_slug: str
    description: str
    status: NodeStatus
    depends_on: list[NodeId]
    output: str | None
    error: str | None

    model_config = {"frozen": True}


class CleanupResult(BaseModel):
    """Result of cleaning up a cancelled task execution."""

    run_id: RunId
    node_id: NodeId
    execution_id: UUID | None
    sandbox_released: bool
    execution_row_updated: bool

    model_config = {"frozen": True}
