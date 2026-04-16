"""Tests for TaskCleanupService — idempotent execution-row cancellation.

Separated from SubtaskCancellationService tests because cleanup operates
on execution rows (resources), not graph nodes (state).
"""

from uuid import uuid4

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
