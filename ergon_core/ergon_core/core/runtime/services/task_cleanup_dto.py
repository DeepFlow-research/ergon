"""DTOs for TaskCleanupService."""

from uuid import UUID

from pydantic import BaseModel

from ergon_core.core.persistence.shared.types import NodeId, RunId


class CleanupResult(BaseModel):
    """Result of cleaning up a cancelled task execution."""

    run_id: RunId
    node_id: NodeId
    execution_id: UUID | None
    sandbox_released: bool
    execution_row_updated: bool

    model_config = {"frozen": True}
