"""Public API error types."""

from uuid import UUID


class DependencyError(Exception):
    """A component's required package is not installed."""


class SandboxKindMismatch(TypeError):
    """A task's worker requires a Sandbox subclass that task.sandbox isn't.

    Raised at ``Experiment`` construction time by the public
    sandbox-compatibility validator. The check uses
    ``type(task.worker).requires_sandbox`` as the contract — if a
    worker subclass narrows ``requires_sandbox`` (e.g.
    ``LeanReActWorker.requires_sandbox = LeanSandbox``), the bound
    ``task.sandbox`` must be an instance of that narrower type.
    """

    def __init__(
        self,
        *,
        task_id: UUID,
        component: str,
        required: type,
        actual: type,
    ) -> None:
        super().__init__(
            f"Task {task_id}: {component} requires sandbox of type "
            f"{required.__name__!r}, but got {actual.__name__!r}."
        )
        self.task_id = task_id
        self.component = component
        self.required = required
        self.actual = actual


class CriterionCheckError(Exception):
    """A criterion rejected the run for domain reasons (shape, probes, content).

    Implementations such as :class:`~ergon_core.api.criterion.Criterion` subclasses may raise this
    from verification helpers; the criterion's ``evaluate`` method is expected to catch it and
    return ``CriterionOutcome(passed=False, ...)``. Bugs and infrastructure failures should use
    other exception types so they propagate loudly.
    """


class SandboxNotLiveError(RuntimeError):
    """Raised when a Sandbox method requiring a live runtime is called on a
    sandbox whose ``_runtime`` is ``None``.

    Deliberately loud rather than a silent no-op. The v1 sandbox-lifecycle
    audit found that silent-skip semantics on detach/terminate masked
    double-release and release-before-acquire bugs. v2 surfaces these
    immediately at the call site so they're caught in tests, not in
    production retry-replay traces.

    Cases that raise:

    - ``Sandbox.terminate()`` called before ``provision()`` succeeded.
    - ``Sandbox.terminate()`` called twice.
    - ``Sandbox.detach()`` called before ``_bind_runtime()``.
    - ``Sandbox.detach()`` called twice.
    - ``task.sandbox.run_command(...)`` (or any IO) on a config-only sandbox.

    Lifecycle owners (worker_execute / execute_task) and eval workers must
    track sandbox state explicitly; silently no-oping here only hides bugs.
    """
