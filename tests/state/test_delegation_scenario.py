"""Full 8-step delegation scenario integration test.

Exercises: create parent → add_task ×2 → observe status → abandon one →
add replacement → complete all → verify workflow complete + mutation WAL
integrity + event count.

Runs against SQLite with per-test transaction rollback (no Docker).
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from ergon_core.core.persistence.graph.status_conventions import (
    ABANDONED,
    COMPLETED,
    PENDING,
    RUNNING,
    TERMINAL_STATUSES,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import (
    AbandonTaskCommand,
    AddTaskCommand,
)
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)
from sqlmodel import Session

from tests.state.mocks import FakeInngestClient

META = MutationMeta(actor="test", reason="scenario-setup")


def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    key: str,
    *,
    status: str = PENDING,
    instance_key: str = "inst-0",
):
    return repo.add_node(
        session,
        run_id,
        task_key=key,
        instance_key=instance_key,
        description=f"node {key}",
        status=status,
        meta=META,
    )


class TestFullDelegationScenario:
    """Manager spawns 2 children, abandons one, spawns replacement,
    all complete → workflow complete."""

    @pytest.mark.asyncio
    async def test_full_delegation_scenario(self, session: Session):
        fake_inngest = FakeInngestClient()
        graph_repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=graph_repo)

        run_id = uuid4()
        definition_id = uuid4()

        # Setup: create parent node (simulating the manager's own node)
        parent = _add_node(
            graph_repo,
            session,
            run_id,
            "manager",
            status=RUNNING,
            instance_key="bench-1",
        )

        # ── Step 1-2: Manager spawns two children ──────────────
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            child1 = svc.add_task(
                session,
                AddTaskCommand(
                    run_id=run_id,
                    definition_id=definition_id,
                    parent_node_id=parent.id,
                    description="research sub-question 1",
                    worker_binding_key="researcher",
                ),
            )
            await svc.dispatch_task_ready(
                run_id=run_id,
                definition_id=definition_id,
                node_id=child1.node_id,
            )

            child2 = svc.add_task(
                session,
                AddTaskCommand(
                    run_id=run_id,
                    definition_id=definition_id,
                    parent_node_id=parent.id,
                    description="research sub-question 2",
                    worker_binding_key="researcher",
                ),
            )
            await svc.dispatch_task_ready(
                run_id=run_id,
                definition_id=definition_id,
                node_id=child2.node_id,
            )

        ready_events = fake_inngest.events_by_name("task/ready")
        assert len(ready_events) == 2

        # ── Step 3: Observe graph state ────────────────────────
        graph = graph_repo.get_graph(session, run_id)
        assert len(graph.nodes) == 3  # parent + 2 children
        assert len(graph.edges) == 2  # parent→child1, parent→child2

        child1_node = graph_repo.get_node(session, run_id=run_id, node_id=child1.node_id)
        child2_node = graph_repo.get_node(session, run_id=run_id, node_id=child2.node_id)
        assert child1_node.status == PENDING
        assert child2_node.status == PENDING

        # ── Step 4: Simulate child1 completing ─────────────────
        graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=child1.node_id,
            new_status=COMPLETED,
            meta=META,
        )
        child1_updated = graph_repo.get_node(session, run_id=run_id, node_id=child1.node_id)
        assert child1_updated.status == COMPLETED

        # ── Step 5: Abandon child2 ────────────────────────────
        abandon_result = svc.abandon_task(
            session,
            AbandonTaskCommand(run_id=run_id, node_id=child2.node_id),
        )
        assert abandon_result.previous_status == PENDING
        assert abandon_result.new_status == ABANDONED

        child2_updated = graph_repo.get_node(session, run_id=run_id, node_id=child2.node_id)
        assert child2_updated.status == ABANDONED

        # ── Step 6: Spawn replacement ──────────────────────────
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            child3 = svc.add_task(
                session,
                AddTaskCommand(
                    run_id=run_id,
                    definition_id=definition_id,
                    parent_node_id=parent.id,
                    description="research sub-question 2 v2",
                    worker_binding_key="researcher",
                ),
            )
            await svc.dispatch_task_ready(
                run_id=run_id,
                definition_id=definition_id,
                node_id=child3.node_id,
            )

        # 3 task/ready events total: child1, child2, child3
        all_ready = fake_inngest.events_by_name("task/ready")
        assert len(all_ready) == 3

        # ── Step 7: Simulate replacement completing ────────────
        graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=child3.node_id,
            new_status=COMPLETED,
            meta=META,
        )

        # ── Step 8: Complete parent ────────────────────────────
        graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=parent.id,
            new_status=COMPLETED,
            meta=META,
        )

        # ── Assertions ────────────────────────────────────────

        # All nodes are terminal
        final_graph = graph_repo.get_graph(session, run_id)
        assert len(final_graph.nodes) == 4  # parent + child1 + child2(abandoned) + child3
        for node in final_graph.nodes:
            assert node.status in TERMINAL_STATUSES, (
                f"Node {node.task_key} has non-terminal status: {node.status}"
            )

        # Specific status checks
        statuses = {n.task_key: n.status for n in final_graph.nodes}
        assert statuses["manager"] == COMPLETED
        assert statuses[child1.task_key] == COMPLETED
        assert statuses[child2.task_key] == ABANDONED
        assert statuses[child3.task_key] == COMPLETED

        # WAL integrity: mutation sequences are contiguous starting from 0
        mutations = graph_repo.get_mutations(session, run_id)
        sequences = [m.sequence for m in mutations]
        assert sequences == list(range(len(sequences))), f"Mutation WAL has gaps: {sequences}"

        # Verify mutation types present
        mutation_types = [m.mutation_type for m in mutations]
        assert mutation_types.count("node.added") == 4  # parent + 3 children
        assert (
            mutation_types.count("edge.added") == 3
        )  # parent→child1, parent→child2, parent→child3
        assert "node.status_changed" in mutation_types

        # Edge integrity: 3 edges (parent → each child)
        assert len(final_graph.edges) == 3
        edge_targets = {e.target_node_id for e in final_graph.edges}
        assert child1.node_id in edge_targets
        assert child2.node_id in edge_targets
        assert child3.node_id in edge_targets
        for edge in final_graph.edges:
            assert edge.source_node_id == parent.id

        # Verify task/ready event payloads carry node_id
        for evt in all_ready:
            assert "node_id" in evt.data
            assert evt.data["node_id"] is not None
