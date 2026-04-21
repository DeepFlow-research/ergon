"""Tests for :class:`SWEBenchSandboxManager` and its template resolution."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.benchmarks.swebench_verified.sandbox.utils import resolve_template
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


# ---------------------------------------------------------------------------
# Reset the singleton between tests — BaseSandboxManager stores _instance and
# per-task dicts at class scope, so leaking state across tests is real.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_sandbox_singleton() -> None:
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    BaseSandboxManager._creation_locks = {}
    BaseSandboxManager._run_ids = {}
    BaseSandboxManager._file_registries = {}
    BaseSandboxManager._created_files_registry = {}
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


# ---------------------------------------------------------------------------
# resolve_template: registry presence vs fallback to default name
# ---------------------------------------------------------------------------


def test_resolve_template_falls_back_to_name_when_registry_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.sandbox.utils.REGISTRY_PATH",
        tmp_path / "does_not_exist.json",
    )
    assert resolve_template() == "ergon-swebench-v1"


def test_resolve_template_prefers_registry_template_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(
        json.dumps(
            {
                "swebench-verified": {
                    "template_id": "tmpl_sw123",
                    "template_name": "ergon-swebench-v1",
                }
            }
        )
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.sandbox.utils.REGISTRY_PATH",
        registry,
    )
    assert resolve_template() == "tmpl_sw123"


def test_resolve_template_falls_back_on_malformed_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text("{not valid json")
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.sandbox.utils.REGISTRY_PATH",
        registry,
    )
    assert resolve_template() == "ergon-swebench-v1"


# ---------------------------------------------------------------------------
# SWEBenchSandboxManager.create threads template= to AsyncSandbox.create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_threads_template_kwarg_to_e2b_sdk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Point the registry lookup at a known template_id.
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(json.dumps({"swebench-verified": {"template_id": "tmpl_pin_sw"}}))
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.sandbox.utils.REGISTRY_PATH",
        registry,
    )

    # Fake AsyncSandbox.create — captures kwargs it was called with.
    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx_fake_sw001"
    fake_sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="git version 2.40\nuv 0.4.0", stderr="")
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

    mgr = SWEBenchSandboxManager()
    assert mgr.template == "tmpl_pin_sw"

    sandbox_id = await mgr.create(task_id=uuid4(), run_id=uuid4(), timeout_minutes=5)
    assert sandbox_id == "sbx_fake_sw001"

    # Verify AsyncSandbox.create was called with template=tmpl_pin_sw.
    fake_create.assert_awaited_once()
    call_kwargs = fake_create.await_args.kwargs
    assert call_kwargs["template"] == "tmpl_pin_sw"
    assert call_kwargs["api_key"] == "test-key"
    assert call_kwargs["timeout"] == 5 * 60

    # Verify setup smoke check ran `git --version`.
    run_calls = fake_sandbox.commands.run.await_args_list
    assert any("git --version" in str(c.args[0]) for c in run_calls)


@pytest.mark.asyncio
async def test_verify_setup_raises_when_git_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.sandbox.utils.REGISTRY_PATH",
        tmp_path / "missing.json",
    )

    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx_broken_sw"

    # Dir-setup mkdir succeeds; the smoke check fails.
    async def _run(cmd: str, **_kwargs: object) -> MagicMock:
        if "git --version" in cmd:
            return MagicMock(exit_code=127, stdout="", stderr="git: command not found")
        return MagicMock(exit_code=0, stdout="", stderr="")

    fake_sandbox.commands.run = AsyncMock(side_effect=_run)
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

    mgr = SWEBenchSandboxManager()
    with pytest.raises(RuntimeError, match="SWE-Bench sandbox smoke check failed"):
        await mgr.create(task_id=uuid4(), run_id=uuid4())
