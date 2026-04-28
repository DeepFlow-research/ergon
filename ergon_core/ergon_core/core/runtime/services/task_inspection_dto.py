"""DTOs for TaskInspectionService — read-only subtask queries."""

from ergon_core.core.persistence.graph.status_conventions import NodeStatus
from ergon_core.core.persistence.shared.types import NodeId
from pydantic import BaseModel


class SubtaskInfo(BaseModel):
    """A snapshot of one subtask suitable for the manager to reason over."""

    node_id: NodeId
    task_slug: str
    description: str
    status: NodeStatus
    depends_on: list[NodeId]
    output: str | None
    error: str | None

    model_config = {"frozen": True}
