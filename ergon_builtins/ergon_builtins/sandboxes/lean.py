"""LeanSandbox — object-bound Lean 4 sandbox for MiniF2F (PR 6 bridge).

Wraps the legacy ``MiniF2FSandboxManager`` (E2B-backed) so the v2
``Task.sandbox`` authoring shape works end to end while the manager
infrastructure is still the source of truth for sandbox lifecycle.

Migration trajectory:

- **PR 10a** extracts ``_ManagerBackedSandboxRuntime`` into
  ``ergon_builtins/sandboxes/_manager_backed.py`` for reuse by
  swebench / researchrubrics / gdpeval ``Sandbox`` subclasses.
- **PR 11** deletes ``MiniF2FSandboxManager`` (and the rest of the
  per-benchmark manager files); ``provision()`` and ``_bind_runtime()``
  here are rewritten to call the E2B SDK directly, and per-task setup
  (currently in ``MiniF2FSandboxManager._install_dependencies``) is
  absorbed into ``provision()``.  ``_ManagerBackedSandboxRuntime``
  has nothing to wrap at that point and is either deleted or rewritten.
"""

from collections.abc import Sequence
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from ergon_core.api.sandbox import Sandbox
from ergon_core.api.sandbox.runtime import CommandResult

# TODO(PR 11): drop this import.  `MiniF2FSandboxManager` is deleted in
# PR 11; `LeanSandbox.provision()` is rewritten to call the E2B SDK
# directly and per-task setup (`_install_dependencies`) moves into
# `provision()` itself.
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager


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


# TODO(PR 10a): extract this class into a shared
# `ergon_builtins/sandboxes/_manager_backed.py` so SWEBench /
# ResearchRubrics / GDPEval `Sandbox` subclasses can reuse it.
# TODO(PR 11): rewrite or delete.  Once `BaseSandboxManager` subclasses
# are gone, this adapter has nothing to wrap — `LeanSandbox.provision()`
# will hold the live E2B handle directly and `_DirectSandboxRuntime`
# becomes the single runtime shape.
class _ManagerBackedSandboxRuntime:
    """Adapter from BaseSandboxManager + AsyncSandbox to SandboxRuntime.

    Used by the ``provision()`` path where the sandbox IS registered in
    the manager's ``_sandboxes`` dict, so manager-mediated ``list_files``
    and ``terminate`` work correctly.
    """

    def __init__(
        self,
        *,
        manager: MiniF2FSandboxManager,
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


# ── LeanSandbox ────────────────────────────────────────────────────────


class LeanSandbox(Sandbox):
    """Lean 4 sandbox for MiniF2F.  Wraps the legacy E2B manager (PR 6 bridge)."""

    lean_version: str = "4.7.0"
    e2b_template: str = "ergon-minif2f-v1"
    requires_network: bool = False
    output_path: str = "/workspace/final_output/"

    async def provision(self) -> None:
        """Provision a fresh Lean sandbox via MiniF2FSandboxManager."""
        # TODO(PR 11): rewrite to call the E2B SDK directly using
        # `self.e2b_template` and absorb `MiniF2FSandboxManager.
        # _install_dependencies` into this method.  The manager-mediated
        # path is the v1 bridge — once PR 11 deletes
        # `MiniF2FSandboxManager`, this body produces an E2B
        # `AsyncSandbox` itself and wraps it in `_DirectSandboxRuntime`.
        manager = MiniF2FSandboxManager()
        sandbox_key = uuid4()
        run_id = uuid4()
        await manager.create(
            sandbox_key,
            run_id,
            envs=self.env if self.env else None,
        )
        live_sandbox = manager.get_sandbox(sandbox_key)
        if live_sandbox is None:
            raise RuntimeError(
                f"MiniF2FSandboxManager.create returned but no sandbox is "
                f"registered for sandbox_key={sandbox_key}"
            )
        runtime = _ManagerBackedSandboxRuntime(
            manager=manager,
            sandbox=cast("_E2BSandboxHandle", live_sandbox),
            sandbox_key=sandbox_key,
        )
        object.__setattr__(self, "_runtime", runtime)

    async def _bind_runtime(self, sandbox_id: str) -> None:
        """Reconnect to an existing E2B sandbox by id (eval-worker path)."""
        # TODO(PR 11): drop the `MiniF2FSandboxManager()` indirection and
        # call `e2b.AsyncSandbox.connect(sandbox_id)` (or equivalent SDK
        # entry point) directly.  The manager is only used here to share
        # the reconnect codepath with the v1 system.
        manager = MiniF2FSandboxManager()
        live_sandbox = await manager.reconnect(sandbox_id)
        runtime = _DirectSandboxRuntime(sandbox=cast("_E2BSandboxHandle", live_sandbox))
        object.__setattr__(self, "_runtime", runtime)
