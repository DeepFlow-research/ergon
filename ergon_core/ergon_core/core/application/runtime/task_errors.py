"""Errors raised by task-domain services."""

from uuid import UUID

from ergon_core.core.application.runtime.errors import GraphError


class DelegationError(GraphError):
    """Base for delegation-specific errors."""

    pass


class TaskRunningError(DelegationError):
    """refine_task called on a node that is currently RUNNING.

    The worker is actively consuming the description; editing it mid-flight
    would produce inconsistent behaviour. The caller should cancel or wait
    for the task to terminate, then refine + restart.
    """

    def __init__(self, task_id: UUID, current_status: str) -> None:
        super().__init__(
            f"Cannot refine node {task_id}: status is '{current_status}' "
            "(refine is blocked while a worker is running)"
        )
        self.task_id = task_id
        self.current_status = current_status


class TaskNotTerminalError(DelegationError):
    """restart_task called on a node that is not in a terminal status.

    Only COMPLETED, FAILED, or CANCELLED nodes can be restarted. A PENDING
    node hasn't run yet; a RUNNING node is live - the manager should cancel
    first if it wants to restart.
    """

    def __init__(self, task_id: UUID, current_status: str) -> None:
        super().__init__(
            f"Cannot restart node {task_id}: status is '{current_status}', "
            "expected one of 'completed', 'failed', 'cancelled'"
        )
        self.task_id = task_id
        self.current_status = current_status


class TaskAlreadyTerminalError(DelegationError):
    """cancel_task called on an already-terminal node."""

    def __init__(self, task_id: UUID, current_status: str) -> None:
        super().__init__(f"Cannot cancel node {task_id}: already terminal ('{current_status}')")
        self.task_id = task_id
        self.current_status = current_status


class SampleRecordMissingError(DelegationError):
    """Raised when a service is asked to mutate a run that has no SampleRecord.

    Every task/graph service mutation must have a SampleRecord. This is
    enforced as a hard invariant so missing fixtures in tests surface as a
    loud failure.
    """

    def __init__(self, sample_id: UUID) -> None:
        super().__init__(
            f"SampleRecord missing for sample_id={sample_id}; seed a SampleRecord before "
            "invoking TaskManagementService.",
        )
        self.sample_id = sample_id
