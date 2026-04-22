"""Exceptions raised by sandbox lifecycle code paths."""


class SandboxSetupError(RuntimeError):
    """Raised when ``BaseSandboxManager._install_dependencies`` cannot complete.

    Carries the original stderr/stdout tail in its message so Inngest
    retries surface actionable errors without digging through logs.
    """
