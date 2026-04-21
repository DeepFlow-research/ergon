"""SubtaskCancellationService — recursive cascade cancel.

Walks the entire descendant subtree of a parent node via BFS and
marks every non-terminal node as CANCELLED in a single transaction.
Returns task/cancelled events for each transitioned node so the
caller can trigger per-node cleanup (sandbox teardown, execution
row update) via Inngest.
"""

import logging
from collections import deque
from typing import Literal
from uuid import UUID

from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    TERMINAL_STATUSES,
)
from ergon_core.core.runtime.events.task_events import TaskCancelledEvent
from ergon_core.core.runtime.services._cancel_helpers import (
    _lookup_benchmark_slug,
    _lookup_sandbox_id,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.subtask_cancellation_dto import CancelOrphansResult

logger = logging.getLogger(__name__)


class SubtaskCancellationService:
    """Recursively cancels all non-terminal descendants of a parent node.

    Uses BFS on parent_node_id to walk the full subtree in one DB
    transaction. This avoids relying on Inngest event chains for
    recursion — a dropped or delayed event can't leave grandchildren
    running under a cancelled parent.

    Separated from TaskCleanupService because cancellation fans out
    (one parent -> N descendants in a single DB transaction) while
    cleanup runs per-node (sandbox teardown, execution row update).

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
        """Recursively cancel every non-terminal descendant of parent_node_id.

        Walks the subtree via BFS on parent_node_id. Each non-terminal
        node is marked CANCELLED with the first-writer-wins guard.
        Returns events for caller to emit after DB commit succeeds —
        each event triggers per-node cleanup (sandbox release, etc).
        """
        meta = MutationMeta(actor="system:cascade", reason=cause)
        transitioned: list[UUID] = []

        queue: deque[UUID] = deque([parent_node_id])
        while queue:
            current_parent = queue.popleft()
            children = session.exec(
                select(RunGraphNode.id, RunGraphNode.status).where(
                    RunGraphNode.run_id == run_id,
                    RunGraphNode.parent_node_id == current_parent,
                )
            ).all()

            for child_id, child_status in children:
                # Always enqueue so we walk the full tree, even past
                # already-terminal nodes (their children might not be).
                queue.append(child_id)

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

        benchmark_slug = _lookup_benchmark_slug(session, run_id)
        events = [
            TaskCancelledEvent(
                run_id=run_id,
                definition_id=definition_id,
                node_id=nid,
                execution_id=_latest_execution_id(session, nid),
                cause=cause,
                sandbox_id=_lookup_sandbox_id(session, _latest_execution_id(session, nid)),
                benchmark_slug=benchmark_slug,
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
