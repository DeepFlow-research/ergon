"""Unit tests for ``BaseSandboxManager.reconnect(sandbox_id)``.

Covers the cross-process reconnect path added for criteria that need to
attach to a still-live task sandbox. See
``docs/rfcs/active/2026-04-17-sandbox-lifetime-covers-criteria.md``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ergon_core.core.providers.sandbox.errors import SandboxExpiredError
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


class _MinimalManager(BaseSandboxManager):
    """Concrete subclass with no-op hooks for unit testing."""

    async def _install_dependencies(self, sandbox: object, task_id: object) -> None:
        return None

    async def _create_directory_structure(
        self,
        sandbox: object,
        sandbox_key: object,
    ) -> None:
        return None

    async def _verify_setup(self, sandbox: object, task_id: object) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
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


@pytest.mark.asyncio
async def test_reconnect_returns_sandbox_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reconnect() returns the AsyncSandbox handle returned by connect()."""
    fake_sandbox = MagicMock()
    fake_connect = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    result = await mgr.reconnect("sbx-live-001")

    assert result is fake_sandbox
    fake_connect.assert_awaited_once_with(
        sandbox_id="sbx-live-001",
        api_key="test-key",
    )


@pytest.mark.asyncio
async def test_reconnect_does_not_register_in_sandboxes_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reconnect() is cross-process only and must NOT populate class state.

    In-process criteria use ``get_sandbox(task_id)`` which reads
    ``_sandboxes``. reconnect is a separate entry point used by
    cross-process callers that hold the returned handle directly.
    """
    fake_sandbox = MagicMock()
    fake_connect = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    await mgr.reconnect("sbx-no-register")

    assert BaseSandboxManager._sandboxes == {}, (
        "reconnect must not populate the in-process _sandboxes dict"
    )


@pytest.mark.asyncio
async def test_reconnect_idempotent_returns_equivalent_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two reconnect() calls for the same sandbox_id each return a handle.

    Both call ``AsyncSandbox.connect`` — the SDK is the source of truth for
    identity. We only assert the manager does not cache between calls and
    doesn't error on a repeat.
    """
    fake_sandbox_a = MagicMock()
    fake_sandbox_b = MagicMock()
    fake_connect = AsyncMock(side_effect=[fake_sandbox_a, fake_sandbox_b])
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    r1 = await mgr.reconnect("sbx-repeat")
    r2 = await mgr.reconnect("sbx-repeat")

    assert r1 is fake_sandbox_a
    assert r2 is fake_sandbox_b
    assert fake_connect.await_count == 2


@pytest.mark.asyncio
async def test_reconnect_raises_sandbox_expired_on_not_found_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SandboxNotFoundException → SandboxExpiredError with sandbox_id preserved."""
    import ergon_core.core.providers.sandbox.manager as mgr_mod

    class _FakeSandboxNotFound(Exception):
        pass

    fake_connect = AsyncMock(side_effect=_FakeSandboxNotFound("E2B says: not found"))
    monkeypatch.setattr(
        mgr_mod,
        "AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(
        mgr_mod,
        "SandboxNotFoundException",
        _FakeSandboxNotFound,
    )
    monkeypatch.setattr(mgr_mod.settings, "e2b_api_key", "test-key")

    mgr = _MinimalManager()
    with pytest.raises(SandboxExpiredError) as exc_info:
        await mgr.reconnect("sbx-expired-001")

    assert exc_info.value.sandbox_id == "sbx-expired-001"
    assert "sbx-expired-001" in str(exc_info.value)


@pytest.mark.asyncio
async def test_reconnect_raises_sandbox_expired_on_timeout_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TimeoutException → SandboxExpiredError."""
    import ergon_core.core.providers.sandbox.manager as mgr_mod

    class _FakeTimeout(Exception):
        pass

    fake_connect = AsyncMock(side_effect=_FakeTimeout("E2B says: timed out"))
    monkeypatch.setattr(
        mgr_mod,
        "AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(mgr_mod, "TimeoutException", _FakeTimeout)
    monkeypatch.setattr(mgr_mod.settings, "e2b_api_key", "test-key")

    mgr = _MinimalManager()
    with pytest.raises(SandboxExpiredError):
        await mgr.reconnect("sbx-timeout-001")


@pytest.mark.asyncio
async def test_reconnect_classifies_by_message_when_sdk_raises_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback: generic Exception whose message mentions '404' / 'expired' /
    'not found' / 'timeout' → SandboxExpiredError.

    Guards against E2B SDK versions whose error classes don't inherit from
    the named exception types above.
    """
    fake_connect = AsyncMock(
        side_effect=Exception("HTTP 404: sandbox not found"),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    with pytest.raises(SandboxExpiredError) as exc_info:
        await mgr.reconnect("sbx-generic-404")

    assert "HTTP 404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_reconnect_reraises_unrelated_errors_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-expiry errors (network blip, auth failure, etc.) propagate as-is.

    We must not silently reclassify unrelated infra errors as
    ``SandboxExpiredError`` — that would hide real bugs behind a benign
    "sandbox-expired" evaluation outcome.
    """
    fake_connect = AsyncMock(side_effect=ConnectionError("TLS handshake failed"))
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    with pytest.raises(ConnectionError, match="TLS handshake failed"):
        await mgr.reconnect("sbx-network-error")
