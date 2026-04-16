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
    """cancel_task called on an already-terminal node."""

    def __init__(self, node_id: UUID, current_status: str) -> None:
        super().__init__(f"Cannot cancel node {node_id}: already terminal ('{current_status}')")
        self.node_id = node_id
        self.current_status = current_status


class CycleDetectedError(DelegationError):
    """Raised when plan_subtasks dependency graph contains a cycle."""

    def __init__(self, remaining_keys: list[str]) -> None:
        super().__init__(f"Cycle detected among keys: {remaining_keys}")
        self.remaining_keys = remaining_keys


class DuplicateLocalKeyError(DelegationError):
    """Raised when plan_subtasks has duplicate local_key values."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Duplicate local_key: {key!r}")
        self.key = key


class UnknownLocalKeyError(DelegationError):
    """Raised when depends_on references a local_key not in the plan."""

    def __init__(self, unknown: list[str]) -> None:
        super().__init__(f"Unknown depends_on keys: {unknown}")
        self.unknown = unknown
