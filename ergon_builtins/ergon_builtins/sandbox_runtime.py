"""Adapters from legacy sandbox managers to public Sandbox instances."""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from pydantic import PrivateAttr

from ergon_core.api import Sandbox
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager, DefaultSandboxManager


class ManagerSandboxRuntime:
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


class ManagerBackedSandbox(Sandbox):
    """Public Sandbox backed by a legacy BaseSandboxManager implementation."""

    manager_cls: ClassVar[type[BaseSandboxManager]] = DefaultSandboxManager

    _manager: BaseSandboxManager | None = PrivateAttr(default=None)
    _run_id: UUID | None = PrivateAttr(default=None)
    _task_id: UUID | None = PrivateAttr(default=None)

    def bind_lifecycle_identity(self, *, run_id: UUID, task_id: UUID) -> None:
        object.__setattr__(self, "_run_id", run_id)
        object.__setattr__(self, "_task_id", task_id)

    async def provision(self) -> None:
        run_id = self._run_id
        task_id = self._task_id
        if run_id is None or task_id is None:
            raise RuntimeError(
                f"{type(self).__name__} must be acquired through SandboxLifecycleHub "
                "so run_id/task_id can be bound before provision()."
            )
        manager = self.manager_cls()
        await manager.create(
            task_id,
            run_id=run_id,
            timeout_minutes=max(1, int((self.timeout_seconds or 1800) / 60)),
            envs=self.env,
            display_task_id=task_id,
        )
        raw_sandbox = manager.get_sandbox(task_id)
        if raw_sandbox is None:
            raise RuntimeError(f"{type(self).__name__} manager did not retain sandbox {task_id}")
        object.__setattr__(self, "_manager", manager)
        object.__setattr__(self, "_runtime", ManagerSandboxRuntime(raw_sandbox))

    async def terminate(self) -> None:
        if self._manager is not None and self._task_id is not None:
            await self._manager.terminate(self._task_id)
        object.__setattr__(self, "_runtime", None)
        object.__setattr__(self, "_manager", None)

    @property
    def raw_sandbox(self) -> Any:  # slopcop: ignore[no-typing-any]
        return self._require_runtime().raw_sandbox

    @property
    def manager(self) -> BaseSandboxManager:
        if self._manager is None:
            self._manager = self.manager_cls()
        return self._manager


class DefaultE2BSandbox(ManagerBackedSandbox):
    """Default E2B-backed sandbox with no benchmark-specific setup."""

    manager_cls: ClassVar[type[BaseSandboxManager]] = DefaultSandboxManager
