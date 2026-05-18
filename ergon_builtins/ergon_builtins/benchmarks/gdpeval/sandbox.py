"""GDPEvalSandbox — object-bound E2B sandbox for GDPEval.

Wraps the legacy ``GDPEvalSandboxManager`` (E2B-backed) so the v2
``Task.sandbox`` authoring shape works end to end while the manager
infrastructure is still the source of truth for sandbox lifecycle.

Migration trajectory:

- **PR 10c** (this PR) introduces ``GDPEvalSandbox`` reusing the shared
  ``_ManagerBackedSandboxRuntime`` adapter PR 10a extracted to
  ``ergon_builtins/sandbox/_manager_backed.py``.
- **PR 11** deletes ``GDPEvalSandboxManager`` (and the rest of the
  per-benchmark manager files); ``provision()`` and ``_bind_runtime()``
  here are rewritten to call the E2B SDK directly, and per-task setup
  (currently in ``GDPEvalSandboxManager._install_dependencies``) is
  absorbed into ``provision()``.
"""

from typing import cast
from uuid import uuid4

from ergon_core.api.sandbox import Sandbox

# TODO(PR 11): drop this import.  ``GDPEvalSandboxManager`` is deleted in
# PR 11; ``GDPEvalSandbox.provision()`` is rewritten to call the E2B SDK
# directly and per-task setup (``_install_dependencies``) moves into
# ``provision()`` itself.
from ergon_builtins.benchmarks.gdpeval.sandbox_manager import (
    GDPEvalSandboxManager,
)
from ergon_builtins.sandbox._manager_backed import (
    _DirectSandboxRuntime,
    _E2BSandboxHandle,
    _ManagerBackedSandboxRuntime,
)


class GDPEvalSandbox(Sandbox):
    """E2B-backed sandbox for GDPEval document-processing tasks.

    Wraps the legacy ``GDPEvalSandboxManager`` (PR 10c bridge). Carries
    config (``template_id`` / ``requires_network`` / ``workspace_dir``)
    that round-trips through ``task_json`` snapshots via the ``_type``
    discriminator inherited from ``Sandbox``.
    """

    template_id: str = "ergon-gdpeval-v1"
    requires_network: bool = False
    workspace_dir: str = "/workspace/gdpeval"

    async def provision(self) -> None:
        """Provision a fresh GDPEval sandbox via GDPEvalSandboxManager."""
        # TODO(PR 11): rewrite to call the E2B SDK directly using
        # ``self.template_id`` and absorb
        # ``GDPEvalSandboxManager._install_dependencies`` into this
        # method.  The manager-mediated path is the v1 bridge — once
        # PR 11 deletes ``GDPEvalSandboxManager``, this body produces
        # an E2B ``AsyncSandbox`` itself and wraps it in
        # ``_DirectSandboxRuntime``.
        manager = GDPEvalSandboxManager()
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
                f"GDPEvalSandboxManager.create returned but no sandbox is "
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
        # TODO(PR 11): drop the ``GDPEvalSandboxManager()`` indirection
        # and call ``e2b.AsyncSandbox.connect(sandbox_id)`` (or
        # equivalent SDK entry point) directly.  The manager is only
        # used here to share the reconnect codepath with the v1 system.
        manager = GDPEvalSandboxManager()
        live_sandbox = await manager.reconnect(sandbox_id)
        runtime = _DirectSandboxRuntime(sandbox=cast("_E2BSandboxHandle", live_sandbox))
        object.__setattr__(self, "_runtime", runtime)
