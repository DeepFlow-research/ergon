"""Errors raised by TaskManagementService delegation tools."""

from uuid import UUID

from ergon_core.core.runtime.errors.graph_errors import GraphError


class DelegationError(GraphError):
    """Base for delegation-specific errors."""

    pass


class TaskNotPendingError(DelegationError):
    """refine_task called on a non-pending node."""

    def __init__(self, node_id: UUID, current_status: str) -> None:
        super().__init__(
            f"Cannot refine node {node_id}: status is '{current_status}', expected 'pending'"
        )
        self.node_id = node_id
        self.current_status = current_status


class TaskAlreadyTerminalError(DelegationError):
    """abandon_task called on an already-terminal node."""

    def __init__(self, node_id: UUID, current_status: str) -> None:
        super().__init__(f"Cannot abandon node {node_id}: already terminal ('{current_status}')")
        self.node_id = node_id
        self.current_status = current_status
