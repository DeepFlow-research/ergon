"""Shared runtime adapters for benchmarks that wrap a BaseSandboxManager.

Two runtime shapes are provided here:

``_ManagerBackedSandboxRuntime`` — **provision-side**.
    Used when ``Sandbox.provision()`` creates the sandbox through a
    ``BaseSandboxManager`` subclass and the sandbox IS registered in the
    manager's ``_sandboxes`` dict.  ``list_files`` and ``close``
    (terminate) are delegated back through the manager so that the
    manager's lifecycle bookkeeping (event sink, WAL entries, registry
    cleanup) fires correctly.

``_DirectSandboxRuntime`` — **eval-side reconnect**.
    Used by ``Sandbox._bind_runtime()`` where the sandbox handle comes
    from ``manager.reconnect()`` and is NOT registered in the manager's
    ``_sandboxes`` dict.  ``list_files`` queries the sandbox directly via
    a ``find`` shell command; ``close`` kills the external sandbox (only
    called if this side is the lifecycle owner, which eval workers
    normally are not).

Both classes wrap an ``_E2BSandboxHandle`` — a lightweight ``Protocol``
over the e2b ``AsyncSandbox`` surface so the adapters stay typed without
importing the SDK at module level.
"""

from collections.abc import Sequence
from typing import Any, Protocol
from uuid import UUID

from ergon_core.api.sandbox.runtime import CommandResult
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager


# ── E2B SDK Protocol boundary ──────────────────────────────────────────
# The e2b SDK doesn't ship a Protocol we can import directly.  We define
# one here at the boundary so the rest of the adapter stays typed.
# ``sandbox_id``, ``commands.run``, ``files.read|write``, ``kill``, and
# ``close`` are stable parts of the e2b SDK surface circa 2026.


class _E2BCommands(Protocol):
    async def run(self, cmd: str, *, timeout: int | None = None) -> Any: ...


class _E2BFiles(Protocol):
    async def read(self, path: str) -> bytes: ...
    async def write(self, path: str, content: bytes) -> None: ...


class _E2BSandboxHandle(Protocol):
    sandbox_id: str
    commands: _E2BCommands
    files: _E2BFiles

    async def kill(self) -> None: ...
    async def close(self) -> None: ...


# ── Runtime adapters ───────────────────────────────────────────────────


# TODO(PR 11): rewrite or delete.  Once `BaseSandboxManager` subclasses
# are gone, this adapter has nothing to wrap — `provision()` will hold
# the live E2B handle directly and `_DirectSandboxRuntime` becomes the
# single runtime shape.
class _ManagerBackedSandboxRuntime:
    """Adapter from BaseSandboxManager + AsyncSandbox to SandboxRuntime.

    Used by the ``provision()`` path where the sandbox IS registered in
    the manager's ``_sandboxes`` dict, so manager-mediated ``list_files``
    and ``terminate`` work correctly.
    """

    def __init__(
        self,
        *,
        manager: BaseSandboxManager,
        sandbox: _E2BSandboxHandle,
        sandbox_key: UUID,
    ) -> None:
        self._manager = manager
        self._sandbox = sandbox
        self._sandbox_key = sandbox_key
        # e2b's AsyncSandbox always carries ``sandbox_id``; the Protocol
        # makes that contract explicit so no getattr fallback is needed.
        self.sandbox_id: str = sandbox.sandbox_id

    async def run_command(
        self,
        cmd: str | Sequence[str],
        *,
        timeout: int | None = None,
    ) -> CommandResult:
        rendered = cmd if isinstance(cmd, str) else " ".join(cmd)
        result = await self._sandbox.commands.run(rendered, timeout=timeout)
        return CommandResult(
            exit_code=result.exit_code,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    async def write_file(self, path: str, content: bytes) -> None:
        # Manager.upload_file expects (task_id, local_path, sandbox_path).
        # We have bytes — use the underlying SDK directly for parity with
        # the v1 path.  PR 10 normalises this on the shared adapter.
        await self._sandbox.files.write(path, content)

    async def read_file(self, path: str) -> bytes:
        return await self._sandbox.files.read(path)

    async def list_files(self, path: str) -> list[str]:
        return await self._manager.list_files(self._sandbox_key, path)

    async def close(self) -> None:
        await self._manager.terminate(self._sandbox_key, reason="completed")

    async def close_local(self) -> None:
        # Drop the local gRPC/TCP connection only; the external sandbox
        # keeps running so sibling eval workers and the orchestrator's
        # final terminate() can still reach it.
        await self._sandbox.close()


class _DirectSandboxRuntime:
    """Lightweight runtime for the eval-side reconnect path.

    Used by ``_bind_runtime()`` where the sandbox handle comes from
    ``manager.reconnect()`` and is NOT registered in the manager's
    ``_sandboxes`` dict.  ``list_files`` queries the sandbox directly;
    ``close`` kills the external sandbox (only called if this side is
    the lifecycle owner, which it normally isn't for eval workers).
    """

    def __init__(self, sandbox: _E2BSandboxHandle) -> None:
        self._sandbox = sandbox
        self.sandbox_id: str = sandbox.sandbox_id

    async def run_command(
        self,
        cmd: str | Sequence[str],
        *,
        timeout: int | None = None,
    ) -> CommandResult:
        rendered = cmd if isinstance(cmd, str) else " ".join(cmd)
        result = await self._sandbox.commands.run(rendered, timeout=timeout)
        return CommandResult(
            exit_code=result.exit_code,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    async def write_file(self, path: str, content: bytes) -> None:
        await self._sandbox.files.write(path, content)

    async def read_file(self, path: str) -> bytes:
        return await self._sandbox.files.read(path)

    async def list_files(self, path: str) -> list[str]:
        result = await self._sandbox.commands.run(
            f"find {path} -type f 2>/dev/null || true", timeout=30
        )
        if not result.stdout:
            return []
        return [line.strip() for line in result.stdout.split("\n") if line.strip()]

    async def close(self) -> None:
        await self._sandbox.kill()

    async def close_local(self) -> None:
        await self._sandbox.close()
