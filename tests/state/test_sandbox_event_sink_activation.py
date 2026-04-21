"""Tests for ``BaseSandboxManager.set_event_sink`` and lifecycle event emission.

Covers the behavior specified in
``docs/rfcs/active/2026-04-17-sandbox-event-sink-activation.md``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from ergon_core.core.providers.sandbox.event_sink import NoopSandboxEventSink
from ergon_core.core.providers.sandbox.manager import (
    AsyncSandbox,
    BaseSandboxManager,
    DefaultSandboxManager,
)

from tests.state.fixtures.recording_event_sink import RecordingSandboxEventSink


class _TestManagerA(BaseSandboxManager):
    """Isolated subclass for testing — never constructed outside this module."""

    async def _install_dependencies(self, sandbox, task_id):  # type: ignore[override]
        pass


class _TestManagerB(BaseSandboxManager):
    """Second isolated subclass — verifies per-class independence."""

    async def _install_dependencies(self, sandbox, task_id):  # type: ignore[override]
        pass


@pytest.fixture(autouse=True)
def reset_test_manager_sinks():
    """Restore noop sink on test managers after each test."""
    yield
    _TestManagerA.set_event_sink(NoopSandboxEventSink())
    _TestManagerB.set_event_sink(NoopSandboxEventSink())


class TestSetEventSink:
    def test_set_event_sink_assigns_to_subclass(self) -> None:
        sink = RecordingSandboxEventSink()
        _TestManagerA.set_event_sink(sink)
        assert _TestManagerA._event_sink is sink

    def test_set_event_sink_does_not_affect_other_subclass(self) -> None:
        sink_a = RecordingSandboxEventSink()
        _TestManagerA.set_event_sink(sink_a)
        assert _TestManagerB._event_sink is not sink_a

    def test_set_event_sink_does_not_affect_base_class(self) -> None:
        sink = RecordingSandboxEventSink()
        _TestManagerA.set_event_sink(sink)
        assert BaseSandboxManager._event_sink is not sink

    def test_default_sink_is_noop(self) -> None:
        assert isinstance(_TestManagerB._event_sink, NoopSandboxEventSink)

    def test_init_no_longer_accepts_event_sink_kwarg(self) -> None:
        """__init__ removing event_sink= means passing it is a TypeError."""
        with pytest.raises(TypeError):
            _TestManagerA(event_sink=RecordingSandboxEventSink())  # type: ignore[call-arg]


@pytest.fixture()
def recording_default_manager(monkeypatch):
    """Install a RecordingSandboxEventSink on DefaultSandboxManager for the test."""
    sink = RecordingSandboxEventSink()
    DefaultSandboxManager.set_event_sink(sink)
    yield DefaultSandboxManager(), sink
    DefaultSandboxManager.set_event_sink(NoopSandboxEventSink())
    DefaultSandboxManager._sandboxes.clear()
    DefaultSandboxManager._run_ids.clear()
    DefaultSandboxManager._file_registries.clear()
    DefaultSandboxManager._created_files_registry.clear()
    DefaultSandboxManager._creation_locks.clear()


@pytest.mark.skipif(AsyncSandbox is None, reason="e2b_code_interpreter not installed")
async def test_sandbox_created_emits_to_sink(
    recording_default_manager,
    monkeypatch,
) -> None:
    """DefaultSandboxManager.create() calls sink.sandbox_created exactly once."""
    from ergon_core.core.providers.sandbox import manager as manager_mod

    manager, sink = recording_default_manager
    task_id = uuid4()
    run_id = uuid4()

    monkeypatch.setattr(manager_mod.settings, "e2b_api_key", "fake-key-for-tests")

    class _FakeSandbox:
        sandbox_id = "sbx-test-123"

    async def _fake_create(**_kwargs):
        return _FakeSandbox()

    monkeypatch.setattr(manager_mod.AsyncSandbox, "create", _fake_create, raising=False)
    monkeypatch.setattr(manager, "_create_directory_structure", AsyncMock())
    monkeypatch.setattr(manager, "_install_dependencies", AsyncMock())
    monkeypatch.setattr(manager, "_verify_setup", AsyncMock())

    await manager.create(
        task_id=task_id,
        run_id=run_id,
        timeout_minutes=5,
    )

    assert len(sink.created) == 1
    assert sink.created[0].sandbox_id == "sbx-test-123"
    assert sink.created[0].run_id == run_id
    assert sink.created[0].task_id == task_id
    assert sink.created[0].timeout_minutes == 5


async def test_sandbox_closed_emits_to_sink(
    recording_default_manager,
) -> None:
    """DefaultSandboxManager.terminate() calls sink.sandbox_closed exactly once."""
    manager, sink = recording_default_manager
    task_id = uuid4()

    class _FakeSandbox:
        sandbox_id = "sbx-test-456"
        kill = AsyncMock()

    manager._sandboxes[task_id] = _FakeSandbox()
    manager._run_ids[task_id] = uuid4()

    await manager.terminate(task_id, reason="completed")

    assert len(sink.closed) == 1
    assert sink.closed[0].sandbox_id == "sbx-test-456"
    assert sink.closed[0].reason == "completed"
    assert sink.closed[0].task_id == task_id


def test_lifespan_wires_all_known_managers() -> None:
    """Every entry in SANDBOX_MANAGERS + DefaultSandboxManager must expose
    ``set_event_sink`` and honor it by assigning to the subclass ``_event_sink``.
    """
    from ergon_builtins.registry import SANDBOX_MANAGERS

    all_managers = [DefaultSandboxManager, *SANDBOX_MANAGERS.values()]
    try:
        for mgr_cls in all_managers:
            assert hasattr(mgr_cls, "set_event_sink"), (
                f"{mgr_cls.__name__} missing set_event_sink — "
                "did it accidentally shadow BaseSandboxManager?"
            )
            sink = RecordingSandboxEventSink()
            mgr_cls.set_event_sink(sink)
            assert mgr_cls._event_sink is sink, (
                f"{mgr_cls.__name__}._event_sink was not updated by set_event_sink"
            )
    finally:
        for mgr_cls in all_managers:
            mgr_cls.set_event_sink(NoopSandboxEventSink())
