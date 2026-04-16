"""Graph mutation listener tests.

Verifies that listeners registered via add_mutation_listener() are
called with the correct RunGraphMutation row after each graph operation.
"""

import asyncio
from uuid import uuid4

import pytest
from ergon_core.core.persistence.graph.models import RunGraphMutation
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from sqlmodel import Session

META = MutationMeta(actor="test-actor", reason="listener-test")


def _make_collecting_listener() -> tuple[list[RunGraphMutation], "asyncio.Future[None]"]:
    """Return (collected_rows, listener_coroutine)."""
    collected: list[RunGraphMutation] = []

    async def listener(row: RunGraphMutation) -> None:
        collected.append(row)

    return collected, listener  # type: ignore[return-value]


def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    key: str,
):
    return repo.add_node(
        session,
        run_id,
        task_key=key,
        instance_key="inst-0",
        description=f"node {key}",
        status="pending",
        meta=META,
    )


@pytest.fixture
def event_loop():
    """Provide an event loop for tests that need asyncio.get_event_loop()."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


class TestMutationListener:
    def test_add_node_fires_listener(self, session: Session, event_loop: asyncio.AbstractEventLoop):
        collected, listener = _make_collecting_listener()
        repo = WorkflowGraphRepository()
        repo.add_mutation_listener(listener)
        run_id = uuid4()

        _add_node(repo, session, run_id, "A")
        event_loop.run_until_complete(asyncio.sleep(0))

        assert len(collected) == 1
        row = collected[0]
        assert row.mutation_type == "node.added"
        assert row.target_type == "node"
        assert row.actor == "test-actor"
        assert row.new_value["task_key"] == "A"
        assert row.new_value["instance_key"] == "inst-0"

    def test_update_node_status_fires_listener(
        self, session: Session, event_loop: asyncio.AbstractEventLoop
    ):
        collected, listener = _make_collecting_listener()
        repo = WorkflowGraphRepository()
        repo.add_mutation_listener(listener)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "A")
        event_loop.run_until_complete(asyncio.sleep(0))
        collected.clear()

        repo.update_node_status(session, run_id=run_id, node_id=node.id, new_status="running", meta=META)
        event_loop.run_until_complete(asyncio.sleep(0))

        assert len(collected) == 1
        row = collected[0]
        assert row.mutation_type == "node.status_changed"
        assert row.target_id == node.id
        assert row.new_value["status"] == "running"
        assert row.old_value["status"] == "pending"

    def test_add_edge_fires_listener(self, session: Session, event_loop: asyncio.AbstractEventLoop):
        collected, listener = _make_collecting_listener()
        repo = WorkflowGraphRepository()
        repo.add_mutation_listener(listener)
        run_id = uuid4()

        a = _add_node(repo, session, run_id, "A")
        b = _add_node(repo, session, run_id, "B")
        event_loop.run_until_complete(asyncio.sleep(0))
        collected.clear()

        edge = repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=b.id,
            status="pending",
            meta=META,
        )
        event_loop.run_until_complete(asyncio.sleep(0))

        assert len(collected) == 1
        row = collected[0]
        assert row.mutation_type == "edge.added"
        assert row.target_type == "edge"
        assert row.target_id == edge.id
        assert row.new_value["source_node_id"] == str(a.id)
        assert row.new_value["target_node_id"] == str(b.id)

    def test_update_node_field_fires_listener(
        self, session: Session, event_loop: asyncio.AbstractEventLoop
    ):
        collected, listener = _make_collecting_listener()
        repo = WorkflowGraphRepository()
        repo.add_mutation_listener(listener)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "A")
        event_loop.run_until_complete(asyncio.sleep(0))
        collected.clear()

        repo.update_node_field(session, run_id=run_id, node_id=node.id, field="description", value="updated desc", meta=META)
        event_loop.run_until_complete(asyncio.sleep(0))

        assert len(collected) == 1
        row = collected[0]
        assert row.mutation_type == "node.field_changed"
        assert row.new_value["field"] == "description"
        assert row.new_value["value"] == "updated desc"

    def test_multiple_listeners_all_called(
        self, session: Session, event_loop: asyncio.AbstractEventLoop
    ):
        collected_a, listener_a = _make_collecting_listener()
        collected_b, listener_b = _make_collecting_listener()
        repo = WorkflowGraphRepository()
        repo.add_mutation_listener(listener_a)
        repo.add_mutation_listener(listener_b)
        run_id = uuid4()

        _add_node(repo, session, run_id, "A")
        event_loop.run_until_complete(asyncio.sleep(0))

        assert len(collected_a) == 1
        assert len(collected_b) == 1

    def test_failing_listener_does_not_break_mutation(
        self, session: Session, event_loop: asyncio.AbstractEventLoop
    ):
        async def bad_listener(row: RunGraphMutation) -> None:
            raise RuntimeError("boom")

        collected, good_listener = _make_collecting_listener()
        repo = WorkflowGraphRepository()
        repo.add_mutation_listener(bad_listener)
        repo.add_mutation_listener(good_listener)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "A")
        event_loop.run_until_complete(asyncio.sleep(0))

        assert node.task_key == "A"
        assert len(collected) == 1
