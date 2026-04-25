"""Block PENDING/READY containment descendants when a parent fails.

Walks the containment axis (parent_node_id) via BFS and marks every
non-terminal, non-running descendant as BLOCKED in a single transaction.
BLOCKED means "predecessor failed; operator action required."

Distinct from SubtaskCancellationService which writes CANCELLED (intentional
stop). BLOCKED is never written by operator actions — only by propagation.
"""

from collections import deque
from uuid import UUID

from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import BLOCKED, RUNNING, TERMINAL_STATUSES
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository


class SubtaskBlockingService:
    """Recursively blocks non-terminal, non-running containment descendants."""

    def __init__(self, graph_repo: WorkflowGraphRepository | None = None) -> None:
        self._graph_repo = graph_repo or WorkflowGraphRepository()

    async def block_pending_descendants(
        self,
        session: Session,
        *,
        run_id: UUID,
        parent_node_id: UUID,
        cause: str,
    ) -> list[UUID]:
        """Recursively BLOCK all PENDING/READY descendants of parent_node_id.

        RUNNING descendants are skipped — live executions continue to their
        own terminal. Terminal descendants are skipped via only_if_not_terminal.

        Returns IDs of nodes that were transitioned to BLOCKED.
        """
        meta = MutationMeta(actor="system:cascade", reason=cause)
        blocked: list[UUID] = []

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
                queue.append(child_id)  # always recurse into grandchildren

                if child_status == RUNNING or child_status in TERMINAL_STATUSES:
                    continue

                applied = await self._graph_repo.update_node_status(
                    session,
                    run_id=run_id,
                    node_id=child_id,
                    new_status=BLOCKED,
                    meta=meta,
                    only_if_not_terminal=True,
                )
                if applied:
                    blocked.append(child_id)

        return blocked
