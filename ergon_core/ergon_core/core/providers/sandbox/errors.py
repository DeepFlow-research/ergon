"""Exceptions raised by sandbox lifecycle code paths."""


class SandboxSetupError(RuntimeError):
    """Raised when ``BaseSandboxManager._install_dependencies`` cannot complete.

    Carries the original stderr/stdout tail in its message so Inngest
    retries surface actionable errors without digging through logs.
    """


class SandboxError(Exception):
    """Base for sandbox infrastructure errors surfaced to callers.

    Distinct from ``SandboxSetupError`` (which is specific to the
    ``_install_dependencies`` step and subclasses ``RuntimeError`` to match
    the existing Inngest retry semantics). ``SandboxError`` is the parent
    for cross-process / lifecycle failure signals (see ``SandboxExpiredError``).
    """


class SandboxExpiredError(SandboxError):
    """Raised when a sandbox is unreachable because it has timed out or
    been terminated.

    Callers (criteria, ``CriterionRuntime``) should catch this and surface
    a ``"sandbox-expired"`` evaluation outcome rather than a generic
    failure. The underlying task output is not lost — the sandbox's state
    was already published to the blob store by the worker's resource
    publisher before the sandbox timed out.
    """

    def __init__(self, sandbox_id: str, detail: str = "") -> None:
        self.sandbox_id = sandbox_id
        msg = f"Sandbox {sandbox_id!r} is expired or not found"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)
