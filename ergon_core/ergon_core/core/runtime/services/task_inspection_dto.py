"""DTOs for TaskInspectionService — read-only subtask queries."""

from typing import Literal

from pydantic import BaseModel

from ergon_core.core.persistence.shared.types import NodeId

SubtaskStatus = Literal["pending", "ready", "running", "completed", "failed", "cancelled"]


class SubtaskInfo(BaseModel):
    """A snapshot of one subtask suitable for the manager to reason over."""

    node_id: NodeId
    task_key: str
    description: str
    status: SubtaskStatus
    depends_on: list[NodeId]
    output: str | None
    error: str | None

    model_config = {"frozen": True}
