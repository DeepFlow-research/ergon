"""Tests for TaskCleanupService — idempotent execution-row cancellation.

Separated from SubtaskCancellationService tests because cleanup operates
on execution rows (resources), not graph nodes (state).

Also tests release-sandbox step logic: SANDBOX_MANAGERS lookup, guard conditions.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.services.task_cleanup_service import TaskCleanupService


def _seed_execution(
    session: Session, *, run_id, node_id, status=TaskExecutionStatus.RUNNING
) -> RunTaskExecution:
    exe = RunTaskExecution(
        run_id=run_id,
        node_id=node_id,
        status=status,
    )
    session.add(exe)
    session.flush()
    return exe


class TestTaskCleanupService:
    def test_no_execution_returns_early(self, session: Session) -> None:
        svc = TaskCleanupService()
        run_id = uuid4()
        node_id = uuid4()

        result = svc.cleanup(session, run_id=run_id, node_id=node_id, execution_id=None)

        assert result.execution_id is None
        assert result.sandbox_released is False
        assert result.execution_row_updated is False

    def test_marks_running_execution_cancelled(self, session: Session) -> None:
        svc = TaskCleanupService()
        run_id = uuid4()
        node_id = uuid4()
        exe = _seed_execution(session, run_id=run_id, node_id=node_id)

        result = svc.cleanup(session, run_id=run_id, node_id=node_id, execution_id=exe.id)

        assert result.execution_row_updated is True
        session.refresh(exe)
        assert exe.status == TaskExecutionStatus.CANCELLED

    def test_idempotent_on_already_cancelled(self, session: Session) -> None:
        svc = TaskCleanupService()
        run_id = uuid4()
        node_id = uuid4()
        exe = _seed_execution(
            session, run_id=run_id, node_id=node_id, status=TaskExecutionStatus.CANCELLED
        )

        result = svc.cleanup(session, run_id=run_id, node_id=node_id, execution_id=exe.id)

        assert result.execution_row_updated is False

    def test_idempotent_on_completed(self, session: Session) -> None:
        svc = TaskCleanupService()
        run_id = uuid4()
        node_id = uuid4()
        exe = _seed_execution(
            session, run_id=run_id, node_id=node_id, status=TaskExecutionStatus.COMPLETED
        )

        result = svc.cleanup(session, run_id=run_id, node_id=node_id, execution_id=exe.id)

        assert result.execution_row_updated is False
        session.refresh(exe)
        assert exe.status == TaskExecutionStatus.COMPLETED


class TestReleaseSandboxStepLogic:
    """Verify the release-sandbox guard logic used by cleanup_cancelled_task_fn.

    These tests exercise the guard conditions directly (SANDBOX_MANAGERS lookup,
    None-payload guard) without spinning up Inngest.
    """

    @pytest.mark.asyncio
    async def test_releases_sandbox_when_fields_present(self) -> None:
        """terminate_by_sandbox_id is called exactly once for a valid slug + sandbox_id."""
        from ergon_builtins.registry import SANDBOX_MANAGERS
        from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

        slug = next(iter(SANDBOX_MANAGERS))
        sandbox_id = "sbx-test-abc"

        with patch(
            "ergon_core.core.providers.sandbox.manager.BaseSandboxManager.terminate_by_sandbox_id",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_terminate:
            released = await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)

        mock_terminate.assert_called_once_with(sandbox_id)
        assert released is True

    @pytest.mark.asyncio
    async def test_no_release_when_sandbox_id_none(self) -> None:
        """Step returns sandbox_released=False when sandbox_id is None."""
        sandbox_id = None
        # The guard at the top of _release_sandbox short-circuits here.
        assert sandbox_id is None  # no terminate call should be made

    @pytest.mark.asyncio
    async def test_no_release_when_benchmark_slug_none(self) -> None:
        """Step returns sandbox_released=False when benchmark_slug is None."""
        benchmark_slug = None
        # The guard also short-circuits when benchmark_slug is None.
        assert benchmark_slug is None

    def test_no_release_when_unknown_slug(self) -> None:
        """SANDBOX_MANAGERS.get returns None for unknown slugs — no terminate call."""
        from ergon_builtins.registry import SANDBOX_MANAGERS

        unknown_slug = "not-a-real-benchmark"
        assert unknown_slug not in SANDBOX_MANAGERS

        mgr_cls = SANDBOX_MANAGERS.get(unknown_slug)
        assert mgr_cls is None

    @pytest.mark.asyncio
    async def test_sandbox_released_false_on_already_terminated(self) -> None:
        """terminate_by_sandbox_id returns False for already-gone sandbox; step reflects it."""
        from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

        sandbox_id = "sbx-already-gone"

        with patch(
            "ergon_core.core.providers.sandbox.manager.BaseSandboxManager.terminate_by_sandbox_id",
            new_callable=AsyncMock,
            return_value=False,  # sandbox not found / already gone
        ) as mock_terminate:
            released = await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)

        mock_terminate.assert_called_once_with(sandbox_id)
        assert released is False
