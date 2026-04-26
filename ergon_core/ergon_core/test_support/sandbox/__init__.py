"""Test-support sandbox doubles."""

from ergon_core.test_support.sandbox.sentinel import is_stub_sandbox_id

__all__ = ["StubSandboxManager", "is_stub_sandbox_id"]


def __getattr__(name: str) -> object:
    if name == "StubSandboxManager":
        from ergon_core.test_support.sandbox.stub_manager import StubSandboxManager

        return StubSandboxManager
    raise AttributeError(name)
