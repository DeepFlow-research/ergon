"""SubtaskCancellationService — single-level cascade cancel.

Marks non-terminal children of a parent node as CANCELLED and returns
events for the caller to emit. Does NOT recurse — cascade to
grandchildren is driven by Inngest re-delivering task/cancelled.
"""

import logging
from typing import Literal
from uuid import UUID

from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    TERMINAL_STATUSES,
)
from ergon_core.core.runtime.events.task_events import TaskCancelledEvent
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.subtask_cancellation_dto import CancelOrphansResult

logger = logging.getLogger(__name__)


class SubtaskCancellationService:
    """Marks non-terminal children of a parent node as CANCELLED.

    Separated from TaskCleanupService because cancellation fans out
    (one parent -> N children in a single DB transaction) while cleanup
    runs per-node (sandbox teardown, execution row update).

    Separated from TaskManagementService because that service handles
    agent-initiated commands while this service is called exclusively
    by the engine (Inngest cascade function).
    """

    def __init__(self, graph_repo: WorkflowGraphRepository | None = None) -> None:
        self._graph_repo = graph_repo or WorkflowGraphRepository()

    def cancel_orphans(
        self,
        session: Session,
        *,
        run_id: UUID,
        definition_id: UUID,
        parent_node_id: UUID,
        cause: Literal["parent_terminal", "dep_invalidated"],
    ) -> CancelOrphansResult:
        """Mark every non-terminal child of parent_node_id as CANCELLED.

        Returns events for caller to emit after DB commit succeeds.
        Single-level only — grandchild cascade driven by Inngest.
        """
        children = session.exec(
            select(RunGraphNode.id, RunGraphNode.status).where(
                RunGraphNode.run_id == run_id,
                RunGraphNode.parent_node_id == parent_node_id,
            )
        ).all()

        meta = MutationMeta(actor="system:cascade", reason=cause)
        transitioned: list[UUID] = []
        for child_id, child_status in children:
            if child_status in TERMINAL_STATUSES:
                continue
            applied = self._graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=child_id,
                new_status=CANCELLED,
                meta=meta,
                only_if_not_terminal=True,
            )
            if applied:
                transitioned.append(child_id)

        events = [
            TaskCancelledEvent(
                run_id=run_id,
                definition_id=definition_id,
                node_id=nid,
                execution_id=_latest_execution_id(session, nid),
                cause=cause,
            )
            for nid in transitioned
        ]
        return CancelOrphansResult(
            parent_node_id=parent_node_id,
            cancelled_node_ids=transitioned,
            events_to_emit=events,
        )


def _latest_execution_id(session: Session, node_id: UUID) -> UUID | None:
    """Most recent execution for a node, or None.

    Duplicated from task_management_service — both services need it
    independently to populate TaskCancelledEvent.execution_id.
    """
    # reason: deferred to avoid circular import at module level
    from ergon_core.core.persistence.telemetry.models import RunTaskExecution

    exe = session.exec(
        select(RunTaskExecution.id)
        .where(RunTaskExecution.node_id == node_id)
        .order_by(RunTaskExecution.started_at.desc())  # type: ignore[union-attr]
        .limit(1)
    ).first()
    return exe
