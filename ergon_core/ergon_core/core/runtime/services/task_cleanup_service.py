"""TaskCleanupService — releases infrastructure for a CANCELLED task execution.

Separated from SubtaskCancellationService because that service operates
on graph nodes (state transitions, fan-out) while this one operates on
execution resources (sandbox, telemetry, context streams). Different
failure characteristics: a failed sandbox teardown should be retried
for this node without re-cancelling siblings.

Idempotent: every mutating call checks current state before writing.
"""

import logging
from uuid import UUID

from sqlmodel import Session, select

from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.services.task_cleanup_dto import CleanupResult

logger = logging.getLogger(__name__)


class TaskCleanupService:
    """Releases infrastructure for a single CANCELLED task execution.

    Called by the Inngest cleanup_cancelled_task_fn after a
    TaskCancelledEvent. Marks the execution row as CANCELLED; E2B sandbox
    release is not implemented on this path yet.
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
                node_id=node_id,
                execution_id=None,
                sandbox_released=False,
                execution_row_updated=False,
            )

        execution_updated = self._mark_execution_cancelled(session, execution_id)
        session.commit()

        sandbox_released = False

        logger.info(
            "task-cleanup node_id=%s execution_id=%s sandbox=%s",
            node_id,
            execution_id,
            sandbox_released,
        )
        return CleanupResult(
            run_id=run_id,
            node_id=node_id,
            execution_id=execution_id,
            sandbox_released=sandbox_released,
            execution_row_updated=execution_updated,
        )

    def _mark_execution_cancelled(self, session: Session, execution_id: UUID) -> bool:
        """Idempotent: skip if already terminal."""
        exe = session.exec(
            select(RunTaskExecution).where(RunTaskExecution.id == execution_id)
        ).first()
        if exe is None or exe.status in {
            TaskExecutionStatus.COMPLETED,
            TaskExecutionStatus.FAILED,
            TaskExecutionStatus.CANCELLED,
        }:
            return False
        exe.status = TaskExecutionStatus.CANCELLED
        session.add(exe)
        return True
