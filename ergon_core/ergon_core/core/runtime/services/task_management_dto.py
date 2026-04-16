"""DTOs for TaskManagementService — dynamic delegation commands and results.

UUID fields use NewType aliases so type checkers catch cross-field
swaps at the call boundary (e.g. passing a NodeId where a RunId is
expected). Status fields use Literal types to catch typos.
"""

from pydantic import BaseModel, Field

from ergon_core.core.persistence.graph.status_conventions import NodeStatus
from ergon_core.core.persistence.shared.types import DefinitionId, EdgeId, NodeId, RunId


class AddTaskCommand(BaseModel):
    """Command to spawn a new sub-task from a running worker."""

    model_config = {"frozen": True}

    run_id: RunId
    definition_id: DefinitionId
    parent_node_id: NodeId
    description: str
    worker_binding_key: str
    task_payload: dict[str, object] = Field(default_factory=dict)


class AddTaskResult(BaseModel):
    """Result of spawning a new sub-task."""

    model_config = {"frozen": True}

    node_id: NodeId
    edge_id: EdgeId
    task_key: str
    status: NodeStatus


class AbandonTaskCommand(BaseModel):
    """Command to abandon a stalling sub-task."""

    model_config = {"frozen": True}

    run_id: RunId
    node_id: NodeId


class AbandonTaskResult(BaseModel):
    model_config = {"frozen": True}

    node_id: NodeId
    previous_status: NodeStatus
    new_status: NodeStatus


class RefineTaskCommand(BaseModel):
    """Command to update description on a pending sub-task."""

    model_config = {"frozen": True}

    run_id: RunId
    node_id: NodeId
    new_description: str


class RefineTaskResult(BaseModel):
    model_config = {"frozen": True}

    node_id: NodeId
    old_description: str
    new_description: str
