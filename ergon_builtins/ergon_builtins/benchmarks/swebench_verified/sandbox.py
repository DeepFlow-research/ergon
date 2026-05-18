"""SWEBenchSandbox — object-bound E2B sandbox for SWE-Bench Verified.

Wraps the legacy ``SWEBenchSandboxManager`` (E2B-backed) so the v2
``Task.sandbox`` authoring shape works end to end while the manager
infrastructure is still the source of truth for sandbox lifecycle.

Migration trajectory:

- **PR 10a** (this PR) introduces ``SWEBenchSandbox`` reusing the shared
  ``ManagerBackedSandboxRuntime`` adapter at
  ``ergon_builtins/sandbox/_manager_backed.py``.
- **PR 11** deletes ``SWEBenchSandboxManager`` (and the rest of the
  per-benchmark manager files); ``provision()`` and ``_bind_runtime()``
  here are rewritten to call the E2B SDK directly, and per-task setup
  (currently in ``SWEBenchSandboxManager._install_dependencies``) is
  absorbed into ``provision()``.
"""

from typing import cast
from uuid import uuid4

from ergon_core.api.sandbox import Sandbox

# TODO(PR 11): drop this import.  `SWEBenchSandboxManager` is deleted in
# PR 11; `SWEBenchSandbox.provision()` is rewritten to call the E2B SDK
# directly and per-task setup (`_install_dependencies`) moves into
# `provision()` itself.
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.sandbox._manager_backed import (
    _DirectSandboxRuntime,
    _E2BSandboxHandle,
    _ManagerBackedSandboxRuntime,
)


class SWEBenchSandbox(Sandbox):
    """E2B-backed sandbox for SWE-Bench Verified instances.

    Wraps the legacy ``SWEBenchSandboxManager`` (PR 10a bridge).
    """

    image_tag: str = "ergon-swebench-v1"
    repo_url: str | None = None
    base_commit: str | None = None
    requires_network: bool = True

    async def provision(self) -> None:
        """Provision a fresh SWE-Bench sandbox via SWEBenchSandboxManager."""
        # TODO(PR 11): rewrite to call the E2B SDK directly using
        # `self.image_tag` and absorb `SWEBenchSandboxManager.
        # _install_dependencies` into this method.  The manager-mediated
        # path is the v1 bridge — once PR 11 deletes
        # `SWEBenchSandboxManager`, this body produces an E2B
        # `AsyncSandbox` itself and wraps it in `_DirectSandboxRuntime`.
        manager = SWEBenchSandboxManager()
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
                f"SWEBenchSandboxManager.create returned but no sandbox is "
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
        # TODO(PR 11): drop the `SWEBenchSandboxManager()` indirection and
        # call `e2b.AsyncSandbox.connect(sandbox_id)` (or equivalent SDK
        # entry point) directly.  The manager is only used here to share
        # the reconnect codepath with the v1 system.
        manager = SWEBenchSandboxManager()
        live_sandbox = await manager.reconnect(sandbox_id)
        runtime = _DirectSandboxRuntime(sandbox=cast("_E2BSandboxHandle", live_sandbox))
        object.__setattr__(self, "_runtime", runtime)
