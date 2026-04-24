"""Local sandbox implementation for canonical smoke tests.

Smoke tests validate Ergon's orchestration, persistence, WAL, and dashboard
surface. They should not consume live E2B quota, especially in CI where stale
remote sandboxes can make unrelated smoke runs fail with account-level limits.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from uuid import UUID

from ergon_core.core.providers.sandbox.manager import AsyncSandbox, BaseSandboxManager
from ergon_core.core.settings import settings

_SMOKE_SANDBOX_PREFIX = "smoke-sandbox-"


@dataclass(frozen=True)
class _CommandResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


@dataclass(frozen=True)
class _EntryInfo:
    name: str


class _SmokeFiles:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _host_path(self, sandbox_path: str) -> Path:
        return self._root / sandbox_path.lstrip("/")

    async def write(self, path: str, content: object, *args: object, **kwargs: object) -> None:
        host_path = self._host_path(path)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            data = content.encode("utf-8")
        elif isinstance(content, bytes):
            data = content
        else:
            data = str(content).encode("utf-8")
        host_path.write_bytes(data)

    async def read(self, path: str, *args: object, **kwargs: object) -> bytes:
        host_path = self._host_path(path)
        if not host_path.exists():
            raise FileNotFoundError(path)
        return host_path.read_bytes()

    async def list(self, path: str, *args: object, **kwargs: object) -> Sequence[_EntryInfo]:
        host_path = self._host_path(path)
        if not host_path.exists():
            raise FileNotFoundError(path)
        return [_EntryInfo(child.name) for child in sorted(host_path.iterdir()) if child.is_file()]


class _SmokeCommands:
    def __init__(self, files: _SmokeFiles) -> None:
        self._files = files

    async def run(self, command: str, *args: object, **kwargs: object) -> _CommandResult:
        if command.startswith("wc -l "):
            path = command.removeprefix("wc -l ").strip()
            content = (await self._files.read(path)).decode("utf-8")
            return _CommandResult(stdout=f"{len(content.splitlines())} {path}\n")
        if "wc -l < /tmp/smoke_health.md" in command:
            return _CommandResult(stdout="OK\n")
        if command.startswith("lean --check "):
            return _CommandResult()
        if command.startswith("python -m py_compile ") or "python /tmp/smoke_health.py" in command:
            return _CommandResult(stdout="8.0.0\n" if "pytest" in command else "")
        if command.startswith("mkdir -p ") or command.startswith("rm -f "):
            return _CommandResult()
        return _CommandResult()


class SmokeSandbox:
    """Small subset of the AsyncSandbox surface used by smoke fixtures."""

    def __init__(self, sandbox_id: str, root: Path) -> None:
        self.sandbox_id = sandbox_id
        self.files = _SmokeFiles(root)
        self.commands = _SmokeCommands(self.files)

    async def set_timeout(self, *args: object, **kwargs: object) -> None:
        return None

    async def kill(self) -> None:
        return None

    async def run_code(self, code: str, *args: object, **kwargs: object) -> object:
        return SimpleNamespace(error=None, logs=SimpleNamespace(stdout=[], stderr=[]))


class SmokeSandboxManager(BaseSandboxManager):
    """Sandbox manager that keeps smoke execution local to the test process."""

    _sandbox_ids: dict[str, UUID] = {}
    _tempdirs: dict[UUID, TemporaryDirectory[str]] = {}

    async def create(
        self,
        sandbox_key: UUID,
        run_id: UUID,
        timeout_minutes: int = 30,
        envs: dict[str, str] | None = None,
        display_task_id: UUID | None = None,
    ) -> str:
        display_task_id = display_task_id or sandbox_key
        if sandbox_key in self._sandboxes:
            return self._sandboxes[sandbox_key].sandbox_id

        sandbox_id = f"{_SMOKE_SANDBOX_PREFIX}{sandbox_key}"
        tempdir = TemporaryDirectory(prefix="ergon-smoke-sandbox-")
        root = Path(tempdir.name)
        for path in ("/inputs", "/workspace/scratchpad", "/workspace/final_output", "/tmp"):
            (root / path.lstrip("/")).mkdir(parents=True, exist_ok=True)

        sandbox = SmokeSandbox(sandbox_id, root)
        cast("dict[UUID, SmokeSandbox]", self._sandboxes)[sandbox_key] = sandbox
        self._sandbox_ids[sandbox_id] = sandbox_key
        self._tempdirs[sandbox_key] = tempdir
        self._ensure_registries(sandbox_key)
        self._run_ids[sandbox_key] = run_id
        self._display_task_ids[sandbox_key] = display_task_id
        self._sandbox_manager_classes[sandbox_key] = type(self)

        await self._event_sink.sandbox_created(
            run_id=run_id,
            task_id=display_task_id,
            sandbox_id=sandbox_id,
            timeout_minutes=timeout_minutes,
        )
        await self._emit_wal_entry(
            sandbox_key,
            command="sandbox.created",
            stdout=f"sandbox_id={sandbox_id}\nmode=smoke-local",
            exit_code=0,
            duration_ms=0,
            sandbox_id=sandbox_id,
            task_id=display_task_id,
        )
        return sandbox_id

    async def reconnect(self, sandbox_id: str) -> AsyncSandbox:
        sandbox_key = self._sandbox_ids[sandbox_id]
        return self._sandboxes[sandbox_key]

    async def reset_timeout(self, task_id: UUID, timeout_minutes: int = 30) -> bool:
        return task_id in self._sandboxes

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        return None

    async def terminate(self, task_id: UUID, reason: str = "completed") -> None:
        sandbox = self._sandboxes.pop(task_id, None)
        sandbox_id = (
            sandbox.sandbox_id if sandbox is not None else f"{_SMOKE_SANDBOX_PREFIX}{task_id}"
        )
        display_task_id = self._get_display_task_id(task_id)
        run_id = self._run_ids.get(task_id)
        self._sandbox_ids.pop(sandbox_id, None)
        self._file_registries.pop(task_id, None)
        self._created_files_registry.pop(task_id, None)
        self._run_ids.pop(task_id, None)
        self._display_task_ids.pop(task_id, None)
        self._sandbox_manager_classes.pop(task_id, None)
        tempdir = self._tempdirs.pop(task_id, None)
        if tempdir is not None:
            tempdir.cleanup()
        if run_id is not None:
            await self._event_sink.sandbox_closed(
                task_id=display_task_id,
                sandbox_id=sandbox_id,
                reason=reason,
                run_id=run_id,
            )


def smoke_uses_local_sandbox() -> bool:
    return os.environ.get("ENABLE_TEST_HARNESS") == "1" and settings.e2b_api_key is not None


__all__ = ["SmokeSandbox", "SmokeSandboxManager", "smoke_uses_local_sandbox"]
