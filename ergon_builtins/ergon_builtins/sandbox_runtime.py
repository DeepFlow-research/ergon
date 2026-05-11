"""Adapters from E2B sandboxes to public Sandbox instances."""

from __future__ import annotations

from typing import Any, ClassVar

from ergon_core.api import Sandbox

try:
    from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
except ImportError:
    AsyncSandbox = None  # type: ignore[assignment,misc]


class E2BSandboxRuntime:
    """SandboxRuntime adapter for an E2B AsyncSandbox-like object."""

    def __init__(self, raw_sandbox: Any) -> None:  # slopcop: ignore[no-typing-any]
        self.raw_sandbox = raw_sandbox

    @property
    def sandbox_id(self) -> str:
        return str(self.raw_sandbox.sandbox_id)

    async def run_command(
        self,
        command: str,
        timeout: int = 30,
    ) -> Any:  # slopcop: ignore[no-typing-any]
        return await self.raw_sandbox.commands.run(command, timeout=timeout)

    async def write_file(self, path: str, content: bytes) -> None:
        await self.raw_sandbox.files.write(path, content)

    async def read_file(self, path: str) -> bytes:
        content = await self.raw_sandbox.files.read(path)
        return content.encode() if isinstance(content, str) else content

    async def list_files(self, path: str) -> list[str]:
        files = await self.raw_sandbox.files.list(path)
        return [str(file) for file in files]


class E2BSandbox(Sandbox):
    """Public Sandbox backed directly by an E2B AsyncSandbox."""

    template: ClassVar[str | None] = None

    async def provision(self) -> None:
        if AsyncSandbox is None:
            raise RuntimeError(
                "e2b_code_interpreter is not installed; install the sandbox extra "
                "to provision E2B-backed benchmark sandboxes."
            )
        raw_sandbox = await AsyncSandbox.create(
            template=self.template,
            timeout=max(60, self.timeout_seconds or 1800),
            envs=self.env,
        )
        object.__setattr__(self, "_runtime", E2BSandboxRuntime(raw_sandbox))

    async def terminate(self) -> None:
        if self._runtime is not None:
            await self.raw_sandbox.kill()
        object.__setattr__(self, "_runtime", None)

    @property
    def raw_sandbox(self) -> Any:  # slopcop: ignore[no-typing-any]
        return self._require_runtime().raw_sandbox
