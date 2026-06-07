"""Containment traversal primitives for runtime graph nodes."""

from collections import deque
from uuid import UUID

from ergon_core.core.persistence.graph.models import SampleGraphNode
from sqlmodel import Session, select


def descendants(
    session: Session,
    *,
    sample_id: UUID,
    root_task_id: UUID,
    max_depth: int | None = None,
) -> list[SampleGraphNode]:
    """Return containment descendants under root_task_id in breadth-first order."""
    result: list[SampleGraphNode] = []
    queue: deque[tuple[UUID, int]] = deque([(root_task_id, 0)])

    while queue:
        parent_id, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue

        children = list(
            session.exec(
                select(SampleGraphNode).where(
                    SampleGraphNode.sample_id == sample_id,
                    SampleGraphNode.parent_task_id == parent_id,
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
    sample_id: UUID,
    root_task_id: UUID,
    max_depth: int | None = None,
) -> set[UUID]:
    """Return IDs for containment descendants under root_task_id."""
    return {
        node.task_id
        for node in descendants(
            session,
            sample_id=sample_id,
            root_task_id=root_task_id,
            max_depth=max_depth,
        )
    }
