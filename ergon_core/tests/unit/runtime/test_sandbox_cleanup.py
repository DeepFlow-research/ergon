"""Tests for the sandbox-cleanup Inngest jobs.

These jobs (introduced as a fix for the PR 4 try/finally bug) own the
*termination* side of the sandbox lifecycle.  They listen for the
terminal task events (``task/completed`` / ``task/failed``) and call
``terminate_external_sandbox`` once.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.application.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
)
from ergon_core.core.application.jobs import sandbox_cleanup as sandbox_cleanup_module
from ergon_core.core.infrastructure.sandbox.lifecycle import (
    SandboxTerminationReason,
    SandboxTerminationResult,
)


class _FakeStepCtx:
    """Pretends to be an Inngest context for the cleanup job.

    The job calls ``ctx.step.run("terminate-sandbox", inner)``; we just
    invoke ``inner()`` directly to test the body.
    """

    class _Step:
        async def run(self, _step_id: str, fn):
            return await fn() if hasattr(fn, "__call__") else fn

    def __init__(self) -> None:
        self.step = self._Step()


@pytest.mark.asyncio
async def test_cleanup_on_completed_terminates_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``task/completed`` event with a sandbox_id terminates that sandbox."""
    payload = TaskCompletedEvent(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sbx-completed",
        node_id=uuid4(),
    )

    captured: dict[str, str | None] = {"sandbox_id": None}

    async def fake_terminate(sandbox_id: str) -> SandboxTerminationResult:
        captured["sandbox_id"] = sandbox_id
        return SandboxTerminationResult(
            sandbox_id=sandbox_id,
            terminated=True,
            reason=SandboxTerminationReason.TERMINATED,
        )

    monkeypatch.setattr(sandbox_cleanup_module, "terminate_external_sandbox", fake_terminate)

    result = await sandbox_cleanup_module.run_sandbox_cleanup_on_completed(_FakeStepCtx(), payload)

    assert captured["sandbox_id"] == "sbx-completed"
    assert result == str(SandboxTerminationReason.TERMINATED)


@pytest.mark.asyncio
async def test_cleanup_on_failed_terminates_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``task/failed`` event with a sandbox_id terminates that sandbox."""
    payload = TaskFailedEvent(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        error="boom",
        sandbox_id="sbx-failed",
        node_id=uuid4(),
    )

    captured: dict[str, str | None] = {"sandbox_id": None}

    async def fake_terminate(sandbox_id: str) -> SandboxTerminationResult:
        captured["sandbox_id"] = sandbox_id
        return SandboxTerminationResult(
            sandbox_id=sandbox_id,
            terminated=True,
            reason=SandboxTerminationReason.TERMINATED,
        )

    monkeypatch.setattr(sandbox_cleanup_module, "terminate_external_sandbox", fake_terminate)

    result = await sandbox_cleanup_module.run_sandbox_cleanup_on_failed(_FakeStepCtx(), payload)

    assert captured["sandbox_id"] == "sbx-failed"
    assert result == str(SandboxTerminationReason.TERMINATED)


@pytest.mark.asyncio
async def test_cleanup_on_failed_skips_when_sandbox_id_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure before sandbox-setup carries ``sandbox_id=None``; cleanup is a no-op."""
    payload = TaskFailedEvent(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        error="prepare-failed",
        sandbox_id=None,
        node_id=uuid4(),
    )

    called = False

    async def fake_terminate(_sandbox_id: str) -> SandboxTerminationResult:
        nonlocal called
        called = True
        return SandboxTerminationResult(
            sandbox_id="never",
            terminated=False,
            reason=SandboxTerminationReason.MISSING_ID,
        )

    monkeypatch.setattr(sandbox_cleanup_module, "terminate_external_sandbox", fake_terminate)

    result = await sandbox_cleanup_module.run_sandbox_cleanup_on_failed(_FakeStepCtx(), payload)

    assert called is False, "no-op when sandbox_id is None"
    assert result == "no_sandbox"
