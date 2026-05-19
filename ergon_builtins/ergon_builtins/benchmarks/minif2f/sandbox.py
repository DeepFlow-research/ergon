"""LeanSandbox — object-bound Lean 4 sandbox for MiniF2F (PR 6 bridge).

Wraps the legacy ``MiniF2FSandboxManager`` (E2B-backed) so the v2
``Task.sandbox`` authoring shape works end to end while the manager
infrastructure is still the source of truth for sandbox lifecycle.

Migration trajectory:

- **PR 10a** extracts ``_ManagerBackedSandboxRuntime`` into
  ``ergon_builtins/sandbox/_manager_backed.py`` for reuse by
  swebench / researchrubrics / gdpeval ``Sandbox`` subclasses.
- **PR 11** deletes ``MiniF2FSandboxManager`` (and the rest of the
  per-benchmark manager files); ``provision()`` and ``_bind_runtime()``
  here are rewritten to call the E2B SDK directly, and per-task setup
  (currently in ``MiniF2FSandboxManager._install_dependencies``) is
  absorbed into ``provision()``.  ``_ManagerBackedSandboxRuntime``
  has nothing to wrap at that point and is either deleted or rewritten.
"""

from typing import cast
from uuid import UUID, uuid4

from ergon_core.api.sandbox import Sandbox

# TODO(PR 11): drop this import.  `MiniF2FSandboxManager` is deleted in
# PR 11; `LeanSandbox.provision()` is rewritten to call the E2B SDK
# directly and per-task setup (`_install_dependencies`) moves into
# `provision()` itself.
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.sandbox._manager_backed import (
    _DirectSandboxRuntime,
    _E2BSandboxHandle,
    _ManagerBackedSandboxRuntime,
)


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
