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

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.services.task_cleanup_dto import CleanupResult
from ergon_core.core.utils import utcnow

# Terminal node statuses — writes to ``run_graph_nodes.status`` are
# no-ops when the node is already in one of these.  Matches the
# ``TERMINAL_STATUSES`` constant used by ``WorkflowGraphRepository``;
# inlined here to avoid circular imports with the graph module.
_TERMINAL_NODE_STATUSES = frozenset({"completed", "failed", "cancelled"})

logger = logging.getLogger(__name__)


class TaskCleanupService:
    """Releases infrastructure for a single CANCELLED task execution.

    Called by the Inngest cleanup_cancelled_task_fn after a
    TaskCancelledEvent. Marks the execution row as CANCELLED and
    (eventually) tears down the sandbox.
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
            # No execution row to mark, but the node may still be in a
            # non-terminal state (e.g. prepare failed before creating an
            # execution row).  Cancel the node too so downstream
            # propagation can unblock.
            self._mark_node_cancelled_if_not_terminal(session, node_id)
            session.commit()
            return CleanupResult(
                run_id=run_id,
                node_id=node_id,
                execution_id=None,
                sandbox_released=False,
                execution_row_updated=False,
            )

        execution_updated = self._mark_execution_cancelled(session, execution_id)
        # Execution and node are mirrored: when an execution is cancelled,
        # its node must transition to a terminal status too, otherwise
        # downstream propagation sees an eternally "running" parent and
        # the run wedges in EXECUTING forever.  Observed 2026-04-23 after
        # A1/B landed — task-executions went to CANCELLED but node rows
        # stayed "running" because the cleanup path never touched them.
        self._mark_node_cancelled_if_not_terminal(session, node_id)
        session.commit()

        # slopcop: ignore[no-todo-comment] — sandbox teardown, wire when sandbox management exists
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
        exe.completed_at = utcnow()
        session.add(exe)
        return True

    def _mark_node_cancelled_if_not_terminal(
        self, session: Session, node_id: UUID
    ) -> bool:
        """Transition ``run_graph_nodes.status`` to ``cancelled`` unless
        already terminal.  Idempotent; returns True if the write applied.

        Does NOT emit a ``node.status_changed`` graph mutation event —
        that lives on ``WorkflowGraphRepository.update_node_status`` which
        is async.  The dashboard observability gap is acceptable here
        because the status change is triggered by an Inngest cancel flow
        that already emits ``dashboard/task.status_changed`` via
        ``dashboard_emitter.task_cancelled``.
        """
        node = session.exec(
            select(RunGraphNode).where(RunGraphNode.id == node_id)
        ).first()
        if node is None or node.status in _TERMINAL_NODE_STATUSES:
            return False
        node.status = "cancelled"
        node.updated_at = utcnow()
        session.add(node)
        return True
