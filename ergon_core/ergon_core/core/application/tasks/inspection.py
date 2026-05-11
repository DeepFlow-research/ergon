"""TaskInspectionService — read-only queries over the subtask tree.

Exists as a separate service because inspection has no side effects.
The toolkit can inject it without granting write access.
"""

import logging
from uuid import UUID

from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import COMPLETED, FAILED
from ergon_core.core.application.tasks.models import SubtaskInfo
from ergon_core.core.application.tasks.repository import TaskExecutionRepository
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

_OUTPUT_MAX_CHARS = 512


class TaskInspectionService:
    """Read-only queries over the subtask tree for agent tool calls.

    Returns frozen SubtaskInfo snapshots — the manager agent uses these
    to decide which subtasks to cancel, refine, or wait on.
    """

    def __init__(self) -> None:
        self._task_execution_repo = TaskExecutionRepository()

    def list_subtasks(
        self,
        session: Session,
        *,
        run_id: UUID,
        parent_node_id: UUID | None = None,
        parent_task_id: UUID | None = None,
    ) -> list[SubtaskInfo]:
        """Direct children of a parent node/task, ordered by task_slug.

        Deterministic ordering lets the LLM refer to subtasks by
        position across turns without task_id confusion.
        """
        if parent_node_id is None and parent_task_id is None:
            raise ValueError("parent_node_id or parent_task_id is required")

        parent_filter = (
            RunGraphNode.parent_task_id == parent_task_id
            if parent_task_id is not None
            else RunGraphNode.parent_node_id == parent_node_id
        )
        nodes = session.exec(
            select(RunGraphNode)
            .where(
                RunGraphNode.run_id == run_id,
                parent_filter,
            )
            .order_by(RunGraphNode.task_slug, RunGraphNode.id)
        ).all()
        return [self._hydrate(session, n) for n in nodes]

    def descendants(
        self,
        session: Session,
        *,
        run_id: UUID,
        parent_task_id: UUID,
        max_depth: int = 3,
    ) -> list[SubtaskInfo]:
        """Breadth-first descendants of parent_task_id up to max_depth."""
        if max_depth < 1:
            return []

        results: list[SubtaskInfo] = []
        frontier = [parent_task_id]
        depth = 0
        while frontier and depth < max_depth:
            next_frontier: list[UUID] = []
            for task_id in frontier:
                children = self.list_subtasks(session, run_id=run_id, parent_task_id=task_id)
                results.extend(children)
                next_frontier.extend(child.task_id for child in children)
            frontier = next_frontier
            depth += 1

        return results

    def get_task(
        self,
        session: Session,
        *,
        run_id: UUID,
        task_id: UUID,
    ) -> SubtaskInfo:
        """Single task snapshot by task_id."""
        node = session.exec(
            select(RunGraphNode).where(
                RunGraphNode.run_id == run_id,
                RunGraphNode.task_id == task_id,
            )
        ).one()
        return self._hydrate(session, node)

    def is_descendant(
        self,
        session: Session,
        *,
        run_id: UUID,
        ancestor_task_id: UUID,
        candidate_task_id: UUID,
    ) -> bool:
        """Return whether candidate_task_id is below ancestor_task_id."""
        frontier = [ancestor_task_id]
        seen: set[UUID] = set()

        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            seen.add(current)
            children = session.exec(
                select(RunGraphNode.task_id).where(
                    RunGraphNode.run_id == run_id,
                    RunGraphNode.parent_task_id == current,
                )
            ).all()
            for child_task_id in children:
                if child_task_id == candidate_task_id:
                    return True
                frontier.append(child_task_id)

        return False

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
            task_id=node.task_id,
            task_slug=node.task_slug,
            description=node.description,
            status=node.status,  # type: ignore[arg-type]
            depends_on=list(deps),
            output=output,
            error=error,
        )

    def _latest_output(self, session: Session, node_id: UUID) -> str | None:
        """Truncated final_assistant_message from the most recent execution."""
        exe = self._task_execution_repo.latest_for_node(session, node_id)
        if exe is None or exe.final_assistant_message is None:
            return None
        text = exe.final_assistant_message
        return text if len(text) <= _OUTPUT_MAX_CHARS else text[:_OUTPUT_MAX_CHARS] + "\u2026"

    def _latest_error(self, session: Session, node_id: UUID) -> str | None:
        """Error message from the most recent execution."""
        exe = self._task_execution_repo.latest_for_node(session, node_id)
        if exe is None or exe.error_json is None:
            return None
        return str(exe.error_json.get("message", exe.error_json))
