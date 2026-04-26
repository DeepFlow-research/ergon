"""Test-support sandbox doubles."""

from ergon_core.test_support.sandbox.sentinel import is_stub_sandbox_id

__all__ = ["StubSandboxManager", "is_stub_sandbox_id"]


def __getattr__(
    name: str,
) -> object:  # slopcop: ignore[no-typing-any] -- module-level lazy export hook.
    if name == "StubSandboxManager":
        # reason: avoid importing manager/test doubles unless explicitly requested.
        from ergon_core.test_support.sandbox.stub_manager import (
            StubSandboxManager,
        )

        return StubSandboxManager
    raise AttributeError(name)
