"""DTOs for SubtaskCancellationService."""

from pydantic import BaseModel

from ergon_core.core.persistence.shared.types import NodeId
from ergon_core.core.runtime.events.task_events import TaskCancelledEvent


class CancelOrphansResult(BaseModel):
    """Result of cascade-cancelling non-terminal children of a parent node."""

    parent_node_id: NodeId
    cancelled_node_ids: list[NodeId]
    events_to_emit: list[TaskCancelledEvent]

    model_config = {"frozen": True}
