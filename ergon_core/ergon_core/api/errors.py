"""Public API error types."""

from uuid import UUID


class DependencyError(Exception):
    """A component's required package is not installed."""


class CriterionCheckError(Exception):
    """A criterion rejected the run for domain reasons (shape, probes, content).

    Implementations such as :class:`~ergon_core.api.criterion.Criterion` subclasses may raise this
    from verification helpers; the criterion's ``evaluate`` method is expected to catch it and
    return ``CriterionOutcome(passed=False, ...)``. Bugs and infrastructure failures should use
    other exception types so they propagate loudly.
    """


class TaskNotMaterializedError(RuntimeError):
    """Raised when definition-time code accesses a runtime task id."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class SandboxNotLiveError(RuntimeError):
    """Raised when sandbox IO is called before a runtime is attached."""

    def __init__(self, sandbox_kind: str) -> None:
        super().__init__(
            f"{sandbox_kind} method called before provision(); no live runtime attached."
        )
        self.sandbox_kind = sandbox_kind


class SandboxKindMismatch(TypeError):
    """Raised when a worker, evaluator, or criterion requires another sandbox kind."""

    def __init__(
        self,
        *,
        task_id: UUID,
        component: str,
        required: type[object],
        actual: type[object],
    ) -> None:
        super().__init__(
            f"task {task_id} ({component}) requires a {required.__name__}, got {actual.__name__}"
        )
        self.task_id = task_id
        self.component = component
        self.required = required
        self.actual = actual


class ContainmentViolation(RuntimeError):
    """Raised when a worker context targets a task outside its descendant tree."""

    def __init__(self, *, target: UUID, ancestor: UUID, run_id: UUID) -> None:
        super().__init__(f"task_id={target} is not a descendant of {ancestor} in run {run_id}")
        self.target = target
        self.ancestor = ancestor
        self.run_id = run_id
