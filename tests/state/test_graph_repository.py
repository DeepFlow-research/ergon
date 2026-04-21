"""Graph repository invariant tests.

Each test exercises a structural invariant that, if broken, causes silent
runtime corruption (deadlocks, dangling references, broken audit replay).
"""

from uuid import uuid4

import pytest
from ergon_core.core.runtime.errors.graph_errors import CycleError, DanglingEdgeError
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from sqlmodel import Session

META = MutationMeta(actor="test", reason="state-test")


async def _add_node(repo: WorkflowGraphRepository, session: Session, run_id, key: str):
    return await repo.add_node(
        session,
        run_id,
        task_key=key,
        instance_key="inst-0",
        description=f"node {key}",
        status="pending",
        meta=META,
    )


class TestCycleDetection:
    async def test_add_edge_creating_cycle_raises(self, session: Session):
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A")
        b = await _add_node(repo, session, run_id, "B")
        c = await _add_node(repo, session, run_id, "C")

        await repo.add_edge(
            session, run_id, source_node_id=a.id, target_node_id=b.id, status="pending", meta=META
        )
        await repo.add_edge(
            session, run_id, source_node_id=b.id, target_node_id=c.id, status="pending", meta=META
        )

        with pytest.raises(CycleError):
            await repo.add_edge(
                session,
                run_id,
                source_node_id=c.id,
                target_node_id=a.id,
                status="pending",
                meta=META,
            )

    async def test_self_loop_raises_cycle_error(self, session: Session):
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A")

        with pytest.raises(CycleError):
            await repo.add_edge(
                session,
                run_id,
                source_node_id=a.id,
                target_node_id=a.id,
                status="pending",
                meta=META,
            )


class TestNodeRemoval:
    async def test_remove_node_cleans_connected_edges(self, session: Session):
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A")
        b = await _add_node(repo, session, run_id, "B")
        c = await _add_node(repo, session, run_id, "C")

        await repo.add_edge(
            session, run_id, source_node_id=a.id, target_node_id=b.id, status="pending", meta=META
        )
        await repo.add_edge(
            session, run_id, source_node_id=b.id, target_node_id=c.id, status="pending", meta=META
        )

        await repo.remove_node(
            session, run_id=run_id, node_id=b.id, terminal_status="removed", meta=META
        )

        graph = repo.get_graph(session, run_id)

        node_ids = {n.id for n in graph.nodes}
        assert a.id in node_ids
        assert b.id in node_ids  # node is marked terminal, not deleted
        assert c.id in node_ids

        b_node = repo.get_node(session, run_id=run_id, node_id=b.id)
        assert b_node.status == "removed"

        for edge in graph.edges:
            assert edge.source_node_id != b.id or edge.status == "removed"
            assert edge.target_node_id != b.id or edge.status == "removed"


class TestMutationLog:
    async def test_mutation_log_records_every_change(self, session: Session):
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A")
        b = await _add_node(repo, session, run_id, "B")
        await repo.add_edge(
            session, run_id, source_node_id=a.id, target_node_id=b.id, status="pending", meta=META
        )
        await repo.update_node_status(
            session, run_id=run_id, node_id=a.id, new_status="running", meta=META
        )

        mutations = repo.get_mutations(session, run_id)

        assert len(mutations) == 4
        sequences = [m.sequence for m in mutations]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == 4  # no duplicates

        types = [m.mutation_type for m in mutations]
        assert types == ["node.added", "node.added", "edge.added", "node.status_changed"]


class TestAnnotationWAL:
    async def test_annotation_wal_point_in_time(self, session: Session):
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "A")

        ann1 = await repo.set_annotation(
            session,
            run_id,
            "node",
            node.id,
            "config",
            payload={"v": 1},
            meta=META,
        )
        s1 = ann1.sequence

        await repo.set_annotation(
            session,
            run_id,
            "node",
            node.id,
            "config",
            payload={"v": 2},
            meta=META,
        )

        historical = repo.get_annotation_at(
            session,
            run_id,
            "node",
            node.id,
            "config",
            sequence=s1,
        )
        assert historical == {"v": 1}

        latest = repo.get_annotation(session, run_id, "node", node.id, "config")
        assert latest == {"v": 2}


class TestReferentialIntegrity:
    async def test_add_edge_to_nonexistent_node_raises(self, session: Session):
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A")

        with pytest.raises(DanglingEdgeError):
            await repo.add_edge(
                session,
                run_id,
                source_node_id=a.id,
                target_node_id=uuid4(),
                status="pending",
                meta=META,
            )
