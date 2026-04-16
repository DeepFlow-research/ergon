"""TaskInspectionService — read-only queries over the subtask tree.

Exists as a separate service because inspection has no side effects.
The toolkit can inject it without granting write access.
"""

import logging
from uuid import UUID

from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import COMPLETED, FAILED
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.services.task_inspection_dto import SubtaskInfo

logger = logging.getLogger(__name__)

_OUTPUT_MAX_CHARS = 512


class TaskInspectionService:
    """Read-only queries over the subtask tree for agent tool calls.

    Returns frozen SubtaskInfo snapshots — the manager agent uses these
    to decide which subtasks to cancel, refine, or wait on.
    """

    def list_subtasks(
        self,
        session: Session,
        *,
        run_id: UUID,
        parent_node_id: UUID,
    ) -> list[SubtaskInfo]:
        """Direct children of parent_node_id, ordered by task_key.

        Deterministic ordering lets the LLM refer to subtasks by
        position across turns without node_id confusion.
        """
        nodes = session.exec(
            select(RunGraphNode)
            .where(
                RunGraphNode.run_id == run_id,
                RunGraphNode.parent_node_id == parent_node_id,
            )
            .order_by(RunGraphNode.task_key, RunGraphNode.id)
        ).all()
        return [self._hydrate(session, n) for n in nodes]

    def get_subtask(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> SubtaskInfo:
        """Single subtask snapshot by node_id."""
        node = session.exec(
            select(RunGraphNode).where(
                RunGraphNode.run_id == run_id,
                RunGraphNode.id == node_id,
            )
        ).one()
        return self._hydrate(session, node)

    def _hydrate(self, session: Session, node: RunGraphNode) -> SubtaskInfo:
        """Build a SubtaskInfo from a RunGraphNode, attaching deps and output/error."""
        deps = session.exec(
            select(RunGraphEdge.source_node_id).where(
                RunGraphEdge.target_node_id == node.id,
                RunGraphEdge.run_id == node.run_id,
            )
        ).all()

        output: str | None = None
        error: str | None = None

        if node.status == COMPLETED:
            output = self._latest_output(session, node.id)
        elif node.status == FAILED:
            error = self._latest_error(session, node.id)

        return SubtaskInfo(
            node_id=node.id,
            task_key=node.task_key,
            description=node.description,
            status=node.status,  # type: ignore[arg-type]
            depends_on=list(deps),
            output=output,
            error=error,
        )

    def _latest_output(self, session: Session, node_id: UUID) -> str | None:
        """Truncated output_text from the most recent execution."""
        exe = session.exec(
            select(RunTaskExecution)
            .where(RunTaskExecution.node_id == node_id)
            .order_by(RunTaskExecution.started_at.desc())  # type: ignore[union-attr]
            .limit(1)
        ).first()
        if exe is None or exe.output_text is None:
            return None
        text = exe.output_text
        return text if len(text) <= _OUTPUT_MAX_CHARS else text[:_OUTPUT_MAX_CHARS] + "\u2026"

    def _latest_error(self, session: Session, node_id: UUID) -> str | None:
        """Error message from the most recent execution."""
        exe = session.exec(
            select(RunTaskExecution)
            .where(RunTaskExecution.node_id == node_id)
            .order_by(RunTaskExecution.started_at.desc())  # type: ignore[union-attr]
            .limit(1)
        ).first()
        if exe is None or exe.error_json is None:
            return None
        return str(exe.error_json.get("message", exe.error_json))
