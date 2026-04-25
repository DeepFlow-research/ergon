"""Errors raised by TaskManagementService delegation tools."""

from uuid import UUID

from ergon_core.core.runtime.errors.graph_errors import GraphError


class DelegationError(GraphError):
    """Base for delegation-specific errors."""

    pass


class TaskNotPendingError(DelegationError):
    """refine_task called on a non-pending node.

    Retained for backwards compatibility. ``refine_task`` now accepts any
    non-RUNNING status and raises ``TaskRunningError`` instead; callers
    that relied on this error should update their except clauses.
    """

    def __init__(self, node_id: UUID, current_status: str) -> None:
        super().__init__(
            f"Cannot refine node {node_id}: status is '{current_status}', expected 'pending'"
        )
        self.node_id = node_id
        self.current_status = current_status


class TaskRunningError(DelegationError):
    """refine_task called on a node that is currently RUNNING.

    The worker is actively consuming the description; editing it mid-flight
    would produce inconsistent behaviour. The caller should cancel or wait
    for the task to terminate, then refine + restart.
    """

    def __init__(self, node_id: UUID, current_status: str) -> None:
        super().__init__(
            f"Cannot refine node {node_id}: status is '{current_status}' "
            "(refine is blocked while a worker is running)"
        )
        self.node_id = node_id
        self.current_status = current_status


class TaskNotTerminalError(DelegationError):
    """restart_task called on a node that is not in a terminal status.

    Only COMPLETED, FAILED, or CANCELLED nodes can be restarted. A PENDING
    node hasn't run yet; a RUNNING node is live — the manager should cancel
    first if it wants to restart.
    """

    def __init__(self, node_id: UUID, current_status: str) -> None:
        super().__init__(
            f"Cannot restart node {node_id}: status is '{current_status}', "
            "expected one of 'completed', 'failed', 'cancelled'"
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

    def __init__(self, remaining_slugs: list[str]) -> None:
        super().__init__(f"Cycle detected among task_slugs: {remaining_slugs}")
        self.remaining_slugs = remaining_slugs


class DuplicateTaskSlugError(DelegationError):
    """Raised when plan_subtasks has duplicate task_slug values."""

    def __init__(self, task_slug: str) -> None:
        super().__init__(f"Duplicate task_slug: {task_slug!r}")
        self.task_slug = task_slug


class UnknownTaskSlugError(DelegationError):
    """Raised when depends_on references a task_slug not in the plan."""

    def __init__(self, slugs: list[str]) -> None:
        super().__init__(f"Unknown depends_on task_slugs: {slugs}")
        self.slugs = slugs


class RunRecordMissingError(DelegationError):
    """Raised when a service is asked to mutate a run that has no RunRecord.

    Every run must have a RunRecord (with ``experiment_definition_id``)
    before any task/graph service is invoked on it. This is enforced as a
    hard invariant so that missing fixtures in tests surface as a loud
    failure instead of silently resolving to a sentinel definition id.
    """

    def __init__(self, run_id: UUID) -> None:
        super().__init__(
            f"RunRecord missing for run_id={run_id}; seed a RunRecord before "
            "invoking TaskManagementService.",
        )
        self.run_id = run_id
