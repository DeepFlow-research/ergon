"""Regression: `_install_dependencies` runs exactly once across repeat
`ensure_sandbox()` / `create()` calls for the same key.

RFC 2026-04-22 moves SWE-Bench per-task setup into `_install_dependencies`.
If `BaseSandboxManager.create()` ever stops early-returning on a cached
sandbox, setup scripts would re-run on every criterion-level
`ensure_sandbox()`. That would be silent but expensive — this test keeps
it caught.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


class _ProbeManager(BaseSandboxManager):
    """Tiny subclass that counts `_install_dependencies` invocations."""

    install_calls: int = 0
    template = "test-template"

    async def _create_directory_structure(self, sandbox: object, sandbox_key: UUID) -> None:
        return None

    async def _install_dependencies(self, sandbox: object, task_id: UUID) -> None:
        type(self).install_calls += 1

    async def _verify_setup(self, sandbox: object, task_id: UUID) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_sandbox_singleton() -> None:
    """Reset the `BaseSandboxManager` singleton + class-level caches.

    `BaseSandboxManager` stores `_instance` and per-task dicts at class
    scope. Without this reset, state leaks across tests and previous
    sandbox entries would make the early-return fire before we've even
    called `create` once.
    """
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    BaseSandboxManager._creation_locks = {}
    BaseSandboxManager._run_ids = {}
    BaseSandboxManager._display_task_ids = {}
    BaseSandboxManager._file_registries = {}
    BaseSandboxManager._created_files_registry = {}
    _ProbeManager._instance = None
    _ProbeManager.install_calls = 0
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    _ProbeManager._instance = None


@pytest.mark.asyncio
async def test_install_dependencies_runs_exactly_once_on_repeated_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three `create()` calls for the same `sandbox_key` → `_install_dependencies`
    is called exactly once.

    The invariant: `BaseSandboxManager.create()` must early-return on a
    cached sandbox_key and NOT re-invoke `_install_dependencies`;
    otherwise criterion-level `ensure_sandbox()` calls will silently
    re-run SWE-Bench setup scripts (clone, install, apply harness spec).
    """
    task_id = uuid4()

    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx_probe_001"
    fake_sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))
    fake_sandbox.files.write = AsyncMock()
    fake_sandbox.run_code = AsyncMock(
        return_value=MagicMock(error=None, logs=MagicMock(stdout=[], stderr=[]))
    )

    # Stub out the E2B sandbox creation path used by the base class.
    # `BaseSandboxManager.create()` calls `AsyncSandbox.create(...)` directly
    # (no `_open_async_sandbox` helper exists); we monkey-patch the module-level
    # `AsyncSandbox` binding in `manager.py` to return our fake sandbox.
    fake_create = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=fake_create),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _ProbeManager()
    await mgr.create(sandbox_key=task_id, run_id=task_id, timeout_minutes=30)
    await mgr.create(sandbox_key=task_id, run_id=task_id, timeout_minutes=30)
    await mgr.create(sandbox_key=task_id, run_id=task_id, timeout_minutes=30)

    assert _ProbeManager.install_calls == 1, (
        "BaseSandboxManager.create must early-return on a cached sandbox "
        "and NOT re-invoke _install_dependencies; otherwise criterion-level "
        "ensure_sandbox() calls will silently re-run SWE-Bench setup scripts."
    )
