"""Containment traversal primitives for runtime graph nodes."""

from collections import deque
from uuid import UUID

from ergon_core.core.persistence.graph.models import RunGraphNode
from sqlmodel import Session, select


def descendants(
    session: Session,
    *,
    run_id: UUID,
    root_node_id: UUID,
    max_depth: int | None = None,
) -> list[RunGraphNode]:
    """Return containment descendants under root_node_id in breadth-first order."""
    result: list[RunGraphNode] = []
    queue: deque[tuple[UUID, int]] = deque([(root_node_id, 0)])

    while queue:
        parent_id, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue

        children = list(
            session.exec(
                select(RunGraphNode).where(
                    RunGraphNode.run_id == run_id,
                    RunGraphNode.parent_task_id == parent_id,
                )
            ).all()
        )
        children.sort(key=lambda node: (node.level, node.task_slug, str(node.task_id)))
        result.extend(children)
        queue.extend((child.task_id, depth + 1) for child in children)

    return result


def descendant_ids(
    session: Session,
    *,
    run_id: UUID,
    root_node_id: UUID,
    max_depth: int | None = None,
) -> set[UUID]:
    """Return IDs for containment descendants under root_node_id."""
    return {
        node.task_id
        for node in descendants(
            session,
            run_id=run_id,
            root_node_id=root_node_id,
            max_depth=max_depth,
        )
    }
