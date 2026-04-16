"""DTOs for TaskManagementService — subtask lifecycle commands and results.

UUID fields use NewType aliases so type checkers catch cross-field
swaps at the call boundary.
"""

from pydantic import BaseModel, Field

from ergon_core.core.persistence.shared.types import NodeId, RunId


# ── add_subtask ────────────────────────────────────────────────────────────


class AddSubtaskCommand(BaseModel):
    """Create one subtask under a parent node.

    definition_id is NOT here — the service resolves it from run_id
    at dispatch time.
    """

    run_id: RunId
    parent_node_id: NodeId
    description: str = Field(min_length=1)
    worker_binding_key: str = "researcher"
    depends_on: list[NodeId] = Field(default_factory=list)

    model_config = {"frozen": True}


class AddSubtaskResult(BaseModel):
    """Result snapshot after creating a subtask node."""

    node_id: NodeId
    task_key: str
    status: str

    model_config = {"frozen": True}


# ── plan_subtasks ──────────────────────────────────────────────────────────


class SubtaskSpec(BaseModel):
    """One entry in a plan_subtasks call."""

    local_key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    worker_binding_key: str = "researcher"
    depends_on: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class PlanSubtasksCommand(BaseModel):
    """Batch-create subtasks with local dependency references."""

    run_id: RunId
    parent_node_id: NodeId
    subtasks: list[SubtaskSpec]

    model_config = {"frozen": True}


class PlanSubtasksResult(BaseModel):
    """Maps local_key to created node_id plus identifies root tasks."""

    nodes: dict[str, NodeId]
    roots: list[str]

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
