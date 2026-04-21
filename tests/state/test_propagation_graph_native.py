"""Graph-native propagation tests (Phase 2).

Tests the *_by_node helpers and on_task_completed_by_node directly,
creating nodes and edges via WorkflowGraphRepository (no definition
tables). All state is verified via RunGraphNode.status and
RunGraphMutation rows.
"""

from uuid import uuid4

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.runtime.execution.propagation import (
    is_workflow_complete_v2,
    is_workflow_failed_v2,
    mark_task_completed_by_node,
    on_task_completed_by_node,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from sqlmodel import Session, select

META = MutationMeta(actor="test", reason="graph-native-test")


async def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    key: str,
    *,
    status: str = TaskExecutionStatus.PENDING,
):
    return await repo.add_node(
        session,
        run_id,
        task_key=key,
        instance_key="inst-0",
        description=f"node {key}",
        status=status,
        meta=META,
    )


class TestOnTaskCompletedByNode:
    async def test_finds_dependents_via_edges(self, session: Session):
        """A -> B edge. Complete A. B should appear in newly-ready."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A")
        b = await _add_node(repo, session, run_id, "B")
        await repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=b.id,
            status="pending",
            meta=META,
        )
        session.flush()

        execution_id = uuid4()
        newly_ready = await on_task_completed_by_node(
            session, run_id, a.id, execution_id, graph_repo=repo
        )

        assert b.id in newly_ready

    async def test_multiple_dependencies_waits_for_all(self, session: Session):
        """A -> C, B -> C. Complete A alone: C not ready. Then complete B: C ready."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A")
        b = await _add_node(repo, session, run_id, "B")
        c = await _add_node(repo, session, run_id, "C")
        await repo.add_edge(
            session, run_id, source_node_id=a.id, target_node_id=c.id, status="pending", meta=META
        )
        await repo.add_edge(
            session, run_id, source_node_id=b.id, target_node_id=c.id, status="pending", meta=META
        )
        session.flush()

        after_a = await on_task_completed_by_node(session, run_id, a.id, uuid4(), graph_repo=repo)
        assert c.id not in after_a

        after_b = await on_task_completed_by_node(session, run_id, b.id, uuid4(), graph_repo=repo)
        assert c.id in after_b

    async def test_skips_non_pending_candidates(self, session: Session):
        """A -> B where B is already RUNNING. Complete A. B should NOT appear."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A")
        b = await _add_node(repo, session, run_id, "B", status=TaskExecutionStatus.RUNNING)
        await repo.add_edge(
            session, run_id, source_node_id=a.id, target_node_id=b.id, status="pending", meta=META
        )
        session.flush()

        newly_ready = await on_task_completed_by_node(
            session, run_id, a.id, uuid4(), graph_repo=repo
        )
        assert b.id not in newly_ready

    async def test_leaf_node_returns_empty(self, session: Session):
        """Complete a node with no outgoing edges. Returns empty list."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A")
        session.flush()

        newly_ready = await on_task_completed_by_node(
            session, run_id, a.id, uuid4(), graph_repo=repo
        )
        assert newly_ready == []


class TestIsWorkflowCompleteV2:
    async def test_treats_cancelled_as_terminal(self, session: Session):
        """COMPLETED + COMPLETED + CANCELLED -> workflow complete."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        await _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.COMPLETED)
        await _add_node(repo, session, run_id, "B", status=TaskExecutionStatus.COMPLETED)
        await _add_node(repo, session, run_id, "C", status="cancelled")
        session.flush()

        assert is_workflow_complete_v2(session, run_id) is True

    async def test_running_node_means_not_complete(self, session: Session):
        """COMPLETED + RUNNING -> not complete."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        await _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.COMPLETED)
        await _add_node(repo, session, run_id, "B", status=TaskExecutionStatus.RUNNING)
        session.flush()

        assert is_workflow_complete_v2(session, run_id) is False


class TestIsWorkflowFailedV2:
    async def test_cancelled_is_not_failed(self, session: Session):
        """COMPLETED + CANCELLED -> not failed."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        await _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.COMPLETED)
        await _add_node(repo, session, run_id, "B", status="cancelled")
        session.flush()

        assert is_workflow_failed_v2(session, run_id) is False

    async def test_failed_node_means_workflow_failed(self, session: Session):
        """COMPLETED + FAILED -> failed."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        await _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.COMPLETED)
        await _add_node(repo, session, run_id, "B", status=TaskExecutionStatus.FAILED)
        session.flush()

        assert is_workflow_failed_v2(session, run_id) is True


class TestMarkTaskCompletedByNode:
    async def test_updates_status_and_logs_mutation(self, session: Session):
        """Create a RUNNING node, mark completed, verify status + WAL entry."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.RUNNING)
        session.flush()

        execution_id = uuid4()
        await mark_task_completed_by_node(session, run_id, node.id, execution_id, graph_repo=repo)
        session.flush()

        row = session.get(RunGraphNode, node.id)
        assert row is not None
        assert row.status == TaskExecutionStatus.COMPLETED

        mutations = list(
            session.exec(
                select(RunGraphMutation).where(
                    RunGraphMutation.run_id == run_id,
                    RunGraphMutation.mutation_type == "node.status_changed",
                    RunGraphMutation.target_id == node.id,
                )
            ).all()
        )
        completed_mutations = [
            m for m in mutations if m.new_value.get("status") == TaskExecutionStatus.COMPLETED
        ]
        assert len(completed_mutations) >= 1
        assert completed_mutations[-1].actor == "system:propagation"
