"""TaskCleanupService — releases infrastructure for a CANCELLED task execution.

Task lifecycle mutation lives in TaskManagementService; this service only
handles per-execution cleanup after cancellation events are delivered.
Idempotent: every mutating call checks current state before writing.
"""

import logging
from uuid import UUID

from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.application.tasks.models import CleanupResult
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


class TaskCleanupService:
    """Releases infrastructure for a single CANCELLED task execution.

    Called by the Inngest cleanup_cancelled_task_fn after a
    TaskCancelledEvent. Marks the execution row as CANCELLED and returns
    the sandbox id for the job's release step.
    """

    def cleanup(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        execution_id: UUID | None,
    ) -> CleanupResult:
        """Mark execution CANCELLED and release resources. Idempotent."""
        if execution_id is None:
            return CleanupResult(
                run_id=run_id,
                task_id=node_id,
                execution_id=None,
                sandbox_id=None,
                sandbox_released=False,
                execution_row_updated=False,
            )

        execution = self._execution(session, execution_id)
        sandbox_id = execution.sandbox_id if execution is not None else None
        execution_updated = self._mark_execution_cancelled(session, execution)
        session.commit()

        logger.info(
            "task-cleanup node_id=%s execution_id=%s sandbox_id=%s",
            node_id,
            execution_id,
            sandbox_id,
        )
        return CleanupResult(
            run_id=run_id,
            task_id=node_id,
            execution_id=execution_id,
            sandbox_id=sandbox_id,
            sandbox_released=False,
            execution_row_updated=execution_updated,
        )

    def _execution(self, session: Session, execution_id: UUID) -> RunTaskExecution | None:
        return session.exec(
            select(RunTaskExecution).where(RunTaskExecution.id == execution_id)
        ).first()

    def _mark_execution_cancelled(self, session: Session, exe: RunTaskExecution | None) -> bool:
        """Idempotent: skip if already terminal."""
        if exe is None or exe.status in {
            TaskExecutionStatus.COMPLETED,
            TaskExecutionStatus.FAILED,
            TaskExecutionStatus.CANCELLED,
        }:
            return False
        exe.status = TaskExecutionStatus.CANCELLED
        session.add(exe)
        return True
