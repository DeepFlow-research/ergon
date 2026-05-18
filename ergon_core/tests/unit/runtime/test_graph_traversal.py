from uuid import UUID, uuid4

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.application.graph.traversal import descendant_ids, descendants
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _node(
    session: Session,
    *,
    run_id: UUID,
    slug: str,
    parent_task_id: UUID | None = None,
    status: str = "pending",
) -> RunGraphNode:
    node = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug=slug,
        description=f"Task {slug}",
        status=status,
        parent_task_id=parent_task_id,
    )
    session.add(node)
    session.flush()
    return node


def test_descendants_walks_full_containment_subtree_past_terminal_nodes() -> None:
    session = _session()
    run_id = uuid4()
    root = _node(session, run_id=run_id, slug="root")
    child = _node(session, run_id=run_id, slug="child", parent_task_id=root.id, status="completed")
    grandchild = _node(session, run_id=run_id, slug="grandchild", parent_task_id=child.id)
    sibling = _node(session, run_id=run_id, slug="sibling", parent_task_id=root.id)
    other_run_child = _node(session, run_id=uuid4(), slug="other", parent_task_id=root.id)
    session.commit()

    walked = descendants(session, run_id=run_id, root_node_id=root.id)

    assert [node.id for node in walked] == [child.id, sibling.id, grandchild.id]
    assert other_run_child.id not in {node.id for node in walked}


def test_descendant_ids_respects_max_depth() -> None:
    session = _session()
    run_id = uuid4()
    root = _node(session, run_id=run_id, slug="root")
    child = _node(session, run_id=run_id, slug="child", parent_task_id=root.id)
    grandchild = _node(session, run_id=run_id, slug="grandchild", parent_task_id=child.id)
    session.commit()

    assert descendant_ids(session, run_id=run_id, root_node_id=root.id, max_depth=1) == {child.id}
    assert descendant_ids(session, run_id=run_id, root_node_id=root.id, max_depth=2) == {
        child.id,
        grandchild.id,
    }
