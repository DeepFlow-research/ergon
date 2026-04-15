"""Tests for :class:`MiniF2FSandboxManager` and the ``template`` kwarg
threading added to :class:`BaseSandboxManager`.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.minif2f.sandbox_manager import (
    MiniF2FSandboxManager,
    _resolve_template,
)
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


# ---------------------------------------------------------------------------
# Reset the singleton between tests — BaseSandboxManager stores _instance and
# per-task dicts at class scope, so leaking state across tests is real.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_sandbox_singleton() -> None:
    # Snapshot + clear class-level state so each test starts fresh.
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    BaseSandboxManager._creation_locks = {}
    BaseSandboxManager._run_ids = {}
    BaseSandboxManager._display_task_ids = {}
    BaseSandboxManager._file_registries = {}
    BaseSandboxManager._created_files_registry = {}
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


# ---------------------------------------------------------------------------
# _resolve_template: registry presence vs fallback to default name
# ---------------------------------------------------------------------------


def test_resolve_template_falls_back_to_name_when_registry_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox_manager._REGISTRY_PATH",
        tmp_path / "does_not_exist.json",
    )
    assert _resolve_template() == "ergon-minif2f-v1"


def test_resolve_template_prefers_registry_template_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(
        json.dumps({"minif2f": {"template_id": "tmpl_abc123", "template_name": "ergon-minif2f-v1"}})
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox_manager._REGISTRY_PATH",
        registry,
    )
    assert _resolve_template() == "tmpl_abc123"


def test_resolve_template_falls_back_on_malformed_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text("{not valid json")
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox_manager._REGISTRY_PATH",
        registry,
    )
    assert _resolve_template() == "ergon-minif2f-v1"


# ---------------------------------------------------------------------------
# MiniF2FSandboxManager.create threads template= to AsyncSandbox.create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_threads_template_kwarg_to_e2b_sdk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Point the registry lookup at a known template_id.
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(json.dumps({"minif2f": {"template_id": "tmpl_pin_xyz"}}))
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox_manager._REGISTRY_PATH",
        registry,
    )

    # Fake AsyncSandbox.create — captures kwargs it was called with.
    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx_fake_001"
    fake_sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="Lean 4.29.0", stderr="")
    )
    fake_sandbox.files.write = AsyncMock()
    fake_sandbox.run_code = AsyncMock(
        return_value=MagicMock(error=None, logs=MagicMock(stdout=[], stderr=[]))
    )

    fake_create = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=fake_create),
    )
    # settings.e2b_api_key must be truthy for create() to proceed.
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = MiniF2FSandboxManager()
    assert mgr.template == "tmpl_pin_xyz"

    sandbox_id = await mgr.create(sandbox_key=uuid4(), run_id=uuid4(), timeout_minutes=5)
    assert sandbox_id == "sbx_fake_001"

    # Verify AsyncSandbox.create was called with template=tmpl_pin_xyz.
    fake_create.assert_awaited_once()
    call_kwargs = fake_create.await_args.kwargs
    assert call_kwargs["template"] == "tmpl_pin_xyz"
    assert call_kwargs["api_key"] == "test-key"
    assert call_kwargs["timeout"] == 5 * 60

    # Verify setup smoke check ran `lake env lean --version`.
    run_calls = fake_sandbox.commands.run.await_args_list
    assert any("lake env lean --version" in str(c.args[0]) for c in run_calls)


@pytest.mark.asyncio
async def test_verify_setup_raises_when_lean_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox_manager._REGISTRY_PATH",
        tmp_path / "missing.json",
    )

    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx_broken"
    # Smoke test returns non-zero.
    fake_sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=127, stdout="", stderr="lake: command not found")
    )
    fake_sandbox.files.write = AsyncMock()
    fake_sandbox.run_code = AsyncMock(
        return_value=MagicMock(error=None, logs=MagicMock(stdout=[], stderr=[]))
    )

    fake_create = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=fake_create),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = MiniF2FSandboxManager()
    with pytest.raises(RuntimeError, match="MiniF2F sandbox verification failed"):
        await mgr.create(sandbox_key=uuid4(), run_id=uuid4())


# ---------------------------------------------------------------------------
# Base class template threading is opt-in: other subclasses unaffected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_class_omits_template_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Subclasses that do not set `template` must not get a template kwarg."""

    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx_generic"
    fake_sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))
    fake_sandbox.files.write = AsyncMock()
    fake_sandbox.run_code = AsyncMock(
        return_value=MagicMock(error=None, logs=MagicMock(stdout=[], stderr=[]))
    )
    fake_create = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=fake_create),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    class _TemplatelessManager(BaseSandboxManager):
        async def _install_dependencies(self, sandbox, task_id):  # noqa: ANN001, ARG002
            return None

    mgr = _TemplatelessManager()
    await mgr.create(sandbox_key=uuid4(), run_id=uuid4())

    call_kwargs = fake_create.await_args.kwargs
    assert "template" not in call_kwargs
