"""Public sandbox API: ``Sandbox`` ABC + ``SandboxRuntime`` Protocol."""

from ergon_core.api.sandbox.runtime import CommandResult, SandboxRuntime
from ergon_core.api.sandbox.sandbox import Sandbox

__all__ = ["CommandResult", "Sandbox", "SandboxRuntime"]
