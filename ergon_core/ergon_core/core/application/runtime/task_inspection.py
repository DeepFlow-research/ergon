"""TaskInspectionService — read-only queries over the subtask tree.

Exists as a separate service because inspection has no side effects.
The toolkit can inject it without granting write access.
"""

import logging
from uuid import UUID

from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.application.runtime.graph_traversal import descendants
from ergon_core.core.application.runtime.status import COMPLETED, FAILED
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.application.runtime.task_models import SubtaskInfo
from ergon_core.core.application.runtime.task_execution_repository import TaskExecutionRepository
from ergon_core.core.persistence.shared.db import get_session
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

_OUTPUT_MAX_CHARS = 512


class TaskInspectionService:
    """Read-only queries over the subtask tree for agent tool calls.

    Returns frozen SubtaskInfo snapshots — the manager agent uses these
    to decide which subtasks to cancel, refine, or wait on.
    """

    def __init__(self, graph_repo: RuntimeGraphRepository | None = None) -> None:
        self._task_execution_repo = TaskExecutionRepository()
        self._graph_repo = graph_repo or RuntimeGraphRepository()

    def list_subtasks(
        self,
        session: Session,
        *,
        sample_id: UUID,
        parent_task_id: UUID,
    ) -> list[SubtaskInfo]:
        """Direct children of parent_task_id, ordered by task_slug.

        Deterministic ordering lets the LLM refer to subtasks by
        position across turns without task_id confusion.
        """
        nodes = session.exec(
            select(SampleGraphNode)
            .where(
                SampleGraphNode.sample_id == sample_id,
                SampleGraphNode.parent_task_id == parent_task_id,
            )
            .order_by(SampleGraphNode.task_slug, SampleGraphNode.task_id)
        ).all()
        return [self._hydrate(session, n) for n in nodes]

    def get_subtask(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
    ) -> SubtaskInfo:
        """Single subtask snapshot by task_id."""
        node = session.exec(
            select(SampleGraphNode).where(
                SampleGraphNode.sample_id == sample_id,
                SampleGraphNode.task_id == task_id,
            )
        ).one()
        return self._hydrate(session, node)

    async def descendant_ids(
        self,
        *,
        sample_id: UUID,
        root_task_id: UUID,
    ) -> frozenset[UUID]:
        """Return all task_ids reachable as children/grandchildren of root_task_id."""

        with get_session() as session:
            rows = descendants(session, sample_id=sample_id, root_task_id=root_task_id)
            # Collect IDs inside the session scope to avoid DetachedInstanceError.
            return frozenset(row.task_id for row in rows)

    def _hydrate(self, session: Session, node: SampleGraphNode) -> SubtaskInfo:
        """Build a SubtaskInfo from a SampleGraphNode, attaching deps and output/error."""
        deps = session.exec(
            select(SampleGraphEdge.source_task_id).where(
                SampleGraphEdge.target_task_id == node.task_id,
                SampleGraphEdge.sample_id == node.sample_id,
            )
        ).all()

        output: str | None = None
        error: str | None = None

        if node.status == COMPLETED:
            output = self._latest_output(session, node.task_id)
        elif node.status == FAILED:
            error = self._latest_error(session, node.task_id)

        return SubtaskInfo(
            task_id=node.task_id,
            task_slug=node.task_slug,
            description=node.description,
            status=node.status,  # type: ignore[arg-type]
            depends_on=list(deps),
            output=output,
            error=error,
        )

    def _latest_output(self, session: Session, task_id: UUID) -> str | None:
        """Truncated final_assistant_message from the most recent execution."""
        exe = self._task_execution_repo.latest_for_node(session, task_id)
        if exe is None or exe.final_assistant_message is None:
            return None
        text = exe.final_assistant_message
        return text if len(text) <= _OUTPUT_MAX_CHARS else text[:_OUTPUT_MAX_CHARS] + "\u2026"

    def _latest_error(self, session: Session, task_id: UUID) -> str | None:
        """Error message from the most recent execution."""
        exe = self._task_execution_repo.latest_for_node(session, task_id)
        if exe is None or exe.error_json is None:
            return None
        return str(exe.error_json.get("message", exe.error_json))
