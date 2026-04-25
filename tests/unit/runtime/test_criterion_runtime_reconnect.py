"""``DefaultCriterionRuntime.ensure_sandbox`` prefers reconnect over create.

Regression test for Phase G of the test-refactor program: when a task
sandbox_id is passed to the runtime, ``ensure_sandbox`` must call
``manager.reconnect(sandbox_id)`` for cross-process attachment rather
than spinning up a fresh sandbox.

See docs/architecture/cross_cutting/sandbox_lifecycle.md §invariant 3.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_core.core.providers.sandbox.errors import SandboxExpiredError
from ergon_core.core.runtime.evaluation.criterion_runtime import (
    DefaultCriterionRuntime,
)
from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext


def _runtime(*, sandbox_id: str | None) -> DefaultCriterionRuntime:
    run_id = uuid4()
    manager = MagicMock()
    manager.get_sandbox = MagicMock(return_value=None)
    manager.reconnect = AsyncMock()
    manager.create = AsyncMock(return_value="new-sbx")
    manager.reset_timeout = AsyncMock()

    runtime = DefaultCriterionRuntime(
        context=CriterionContext(run_id=run_id),
        sandbox_manager=manager,
        run_id=run_id,
        sandbox_id=sandbox_id,
    )
    return runtime


@pytest.mark.asyncio
async def test_ensure_sandbox_reconnects_when_sandbox_id_available() -> None:
    """Cross-process path: sandbox_id known → ``manager.reconnect`` called."""
    runtime = _runtime(sandbox_id="sbx-live-001")
    runtime.sandbox_manager.reconnect.return_value = MagicMock()

    await runtime.ensure_sandbox()

    runtime.sandbox_manager.reconnect.assert_awaited_once_with("sbx-live-001")
    runtime.sandbox_manager.create.assert_not_called()
    runtime.sandbox_manager.reset_timeout.assert_not_called()
    assert runtime._reconnected_sandbox is not None
    assert runtime._owns_sandbox is False


@pytest.mark.asyncio
async def test_ensure_sandbox_creates_when_no_sandbox_id_and_no_cache() -> None:
    """Last-resort path: no in-process cache + no sandbox_id → create."""
    runtime = _runtime(sandbox_id=None)

    await runtime.ensure_sandbox()

    runtime.sandbox_manager.reconnect.assert_not_called()
    runtime.sandbox_manager.create.assert_awaited_once()
    assert runtime._owns_sandbox is True


@pytest.mark.asyncio
async def test_ensure_sandbox_uses_in_process_cache_first() -> None:
    """In-process cache hit: reset_timeout, no reconnect, no create."""
    runtime = _runtime(sandbox_id="sbx-ignored-when-cache-hit")
    cached_sandbox = MagicMock()
    runtime.sandbox_manager.get_sandbox = MagicMock(return_value=cached_sandbox)

    await runtime.ensure_sandbox()

    runtime.sandbox_manager.reset_timeout.assert_awaited_once()
    runtime.sandbox_manager.reconnect.assert_not_called()
    runtime.sandbox_manager.create.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_sandbox_propagates_sandbox_expired_from_reconnect() -> None:
    """If the task sandbox is already torn down, reconnect raises
    ``SandboxExpiredError`` and ``ensure_sandbox`` lets it propagate — the
    caller translates to a benign 'sandbox-expired' evaluation outcome."""
    runtime = _runtime(sandbox_id="sbx-expired-001")
    runtime.sandbox_manager.reconnect.side_effect = SandboxExpiredError(
        "sbx-expired-001",
        detail="not found (404)",
    )

    with pytest.raises(SandboxExpiredError):
        await runtime.ensure_sandbox()

    runtime.sandbox_manager.create.assert_not_called()


@pytest.mark.asyncio
async def test_current_sandbox_returns_reconnected_handle() -> None:
    """After cross-process attach, ``_current_sandbox`` returns the
    reconnected handle (not ``None``), so subsequent ``run_command`` /
    ``execute_code`` / ``write_file`` calls have something to act on."""
    runtime = _runtime(sandbox_id="sbx-reconn-001")
    fake_sandbox = MagicMock()
    runtime.sandbox_manager.reconnect.return_value = fake_sandbox

    await runtime.ensure_sandbox()

    assert runtime._current_sandbox() is fake_sandbox


@pytest.mark.asyncio
async def test_current_sandbox_prefers_in_process_over_reconnected() -> None:
    """If the in-process cache ever populates (e.g. ``create`` fires
    later), ``_current_sandbox`` returns the cached handle ahead of the
    reconnected one.  Guards against drift between the two handles."""
    runtime = _runtime(sandbox_id="sbx-both-001")
    reconnected = MagicMock(name="reconnected")
    in_process = MagicMock(name="in_process")
    runtime._reconnected_sandbox = reconnected
    runtime.sandbox_manager.get_sandbox = MagicMock(return_value=in_process)

    assert runtime._current_sandbox() is in_process
