"""Tests for :class:`MiniF2FSandboxManager` and the ``template`` kwarg
threading added to :class:`BaseSandboxManager`.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.sandbox.utils import resolve_template
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.providers.sandbox.event_sink import NoopSandboxEventSink
from tests.state.fixtures.recording_event_sink import RecordingSandboxEventSink


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
    BaseSandboxManager._file_registries = {}
    BaseSandboxManager._created_files_registry = {}
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


# ---------------------------------------------------------------------------
# resolve_template: registry presence vs fallback to default name
# ---------------------------------------------------------------------------


def testresolve_template_falls_back_to_name_when_registry_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox.utils.REGISTRY_PATH",
        tmp_path / "does_not_exist.json",
    )
    assert resolve_template() == "ergon-minif2f-v1"


def testresolve_template_prefers_registry_template_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(
        json.dumps({"minif2f": {"template_id": "tmpl_abc123", "template_name": "ergon-minif2f-v1"}})
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox.utils.REGISTRY_PATH",
        registry,
    )
    assert resolve_template() == "tmpl_abc123"


def testresolve_template_falls_back_on_malformed_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text("{not valid json")
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox.utils.REGISTRY_PATH",
        registry,
    )
    assert resolve_template() == "ergon-minif2f-v1"


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
        "ergon_builtins.benchmarks.minif2f.sandbox.utils.REGISTRY_PATH",
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

    sandbox_id = await mgr.create(task_id=uuid4(), run_id=uuid4(), timeout_minutes=5)
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
        "ergon_builtins.benchmarks.minif2f.sandbox.utils.REGISTRY_PATH",
        tmp_path / "missing.json",
    )

    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx_broken"

    # Dir-setup mkdir succeeds; the `lake env lean --version` smoke check fails.
    async def _run(cmd: str, **_kwargs: object) -> MagicMock:
        if "lake env lean --version" in cmd:
            return MagicMock(exit_code=127, stdout="", stderr="lake: command not found")
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

    mgr = MiniF2FSandboxManager()
    with pytest.raises(RuntimeError, match="MiniF2F sandbox verification failed"):
        await mgr.create(task_id=uuid4(), run_id=uuid4())


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
    await mgr.create(task_id=uuid4(), run_id=uuid4())

    call_kwargs = fake_create.await_args.kwargs
    assert "template" not in call_kwargs


# ---------------------------------------------------------------------------
# RFC: sandbox-manager-key-cleanup — verify task_id is used directly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_uses_task_id_as_event_task_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """After the rename, sandbox_created fires with task_id equal to the
    task_id arg — no display_task_id indirection."""
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(json.dumps({"minif2f": {"template_id": "tmpl_evt_test"}}))
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox.utils.REGISTRY_PATH",
        registry,
    )

    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx_event_test"
    fake_sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="Lean 4.x", stderr="")
    )
    fake_sandbox.files.write = AsyncMock()
    fake_sandbox.run_code = AsyncMock(
        return_value=MagicMock(error=None, logs=MagicMock(stdout=[], stderr=[]))
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=AsyncMock(return_value=fake_sandbox)),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    recording_sink = RecordingSandboxEventSink()
    MiniF2FSandboxManager.set_event_sink(recording_sink)
    try:
        mgr = MiniF2FSandboxManager()
        task_id = uuid4()
        run_id = uuid4()
        await mgr.create(task_id=task_id, run_id=run_id)

        assert len(recording_sink.created) == 1
        event = recording_sink.created[0]
        assert event.task_id == task_id
        assert event.run_id == run_id
    finally:
        MiniF2FSandboxManager.set_event_sink(NoopSandboxEventSink())


@pytest.mark.asyncio
async def test_terminate_fires_closed_with_same_task_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """terminate() emits sandbox_closed with the same task_id passed to create()."""
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(json.dumps({"minif2f": {"template_id": "tmpl_term_test"}}))
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.sandbox.utils.REGISTRY_PATH",
        registry,
    )

    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx_term_test"
    fake_sandbox.kill = AsyncMock()
    fake_sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="Lean 4.x", stderr="")
    )
    fake_sandbox.files.write = AsyncMock()
    fake_sandbox.run_code = AsyncMock(
        return_value=MagicMock(error=None, logs=MagicMock(stdout=[], stderr=[]))
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=AsyncMock(return_value=fake_sandbox)),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    recording_sink = RecordingSandboxEventSink()
    MiniF2FSandboxManager.set_event_sink(recording_sink)
    try:
        mgr = MiniF2FSandboxManager()
        task_id = uuid4()
        await mgr.create(task_id=task_id, run_id=uuid4())
        await mgr.terminate(task_id)

        assert len(recording_sink.closed) == 1
        assert recording_sink.closed[0].task_id == task_id
    finally:
        MiniF2FSandboxManager.set_event_sink(NoopSandboxEventSink())


def test_display_task_ids_attr_absent() -> None:
    """Class-level _display_task_ids must not exist after this RFC."""
    assert not hasattr(BaseSandboxManager, "_display_task_ids")


def test_get_display_task_id_method_absent() -> None:
    """_get_display_task_id must not exist after this RFC."""
    assert not hasattr(BaseSandboxManager, "_get_display_task_id")
