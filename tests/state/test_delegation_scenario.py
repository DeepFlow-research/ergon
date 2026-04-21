"""Full 8-step delegation scenario integration test.

Exercises: create parent -> add_subtask x2 -> observe status -> cancel one ->
add replacement -> complete all -> verify workflow complete + mutation WAL
integrity + event count.

Runs against SQLite with per-test transaction rollback (no Docker).
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    PENDING,
    RUNNING,
    TERMINAL_STATUSES,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import (
    AddSubtaskCommand,
    CancelTaskCommand,
)
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)
from sqlmodel import Session

from tests.state.mocks import FakeInngestClient

META = MutationMeta(actor="test", reason="scenario-setup")


async def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    key: str,
    *,
    status: str = PENDING,
    instance_key: str = "inst-0",
):
    return await repo.add_node(
        session,
        run_id,
        task_key=key,
        instance_key=instance_key,
        description=f"node {key}",
        status=status,
        meta=META,
    )


class TestFullDelegationScenario:
    """Manager spawns 2 children, cancels one, spawns replacement,
    all complete -> workflow complete."""

    async def test_full_delegation_scenario(self, session: Session):
        fake_inngest = FakeInngestClient()
        graph_repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=graph_repo)

        run_id = uuid4()

        # Setup: create parent node (simulating the manager's own node)
        parent = await _add_node(
            graph_repo,
            session,
            run_id,
            "manager",
            status=RUNNING,
            instance_key="bench-1",
        )

        # -- Step 1-2: Manager spawns two children --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            child1 = await svc.add_subtask(
                session,
                AddSubtaskCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    description="research sub-question 1",
                    worker_binding_key="researcher",
                ),
            )

            child2 = await svc.add_subtask(
                session,
                AddSubtaskCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    description="research sub-question 2",
                    worker_binding_key="researcher",
                ),
            )

        # -- Step 3: Observe graph state --
        graph = graph_repo.get_graph(session, run_id)
        assert len(graph.nodes) == 3  # parent + 2 children

        child1_node = graph_repo.get_node(session, run_id=run_id, node_id=child1.node_id)
        child2_node = graph_repo.get_node(session, run_id=run_id, node_id=child2.node_id)
        assert child1_node.status == PENDING
        assert child2_node.status == PENDING

        # -- Step 4: Simulate child1 completing --
        await graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=child1.node_id,
            new_status=COMPLETED,
            meta=META,
        )
        child1_updated = graph_repo.get_node(session, run_id=run_id, node_id=child1.node_id)
        assert child1_updated.status == COMPLETED

        # -- Step 5: Cancel child2 --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            cancel_result = await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=child2.node_id),
            )
        assert cancel_result.old_status == PENDING

        child2_updated = graph_repo.get_node(session, run_id=run_id, node_id=child2.node_id)
        assert child2_updated.status == CANCELLED

        # -- Step 6: Spawn replacement --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            child3 = await svc.add_subtask(
                session,
                AddSubtaskCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    description="research sub-question 2 v2",
                    worker_binding_key="researcher",
                ),
            )

        # -- Step 7: Simulate replacement completing --
        await graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=child3.node_id,
            new_status=COMPLETED,
            meta=META,
        )

        # -- Step 8: Complete parent --
        await graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=parent.id,
            new_status=COMPLETED,
            meta=META,
        )

        # -- Assertions --

        # All nodes are terminal
        final_graph = graph_repo.get_graph(session, run_id)
        assert len(final_graph.nodes) == 4  # parent + child1 + child2(cancelled) + child3
        for node in final_graph.nodes:
            assert node.status in TERMINAL_STATUSES, (
                f"Node {node.task_key} has non-terminal status: {node.status}"
            )

        # Specific status checks
        statuses = {n.task_key: n.status for n in final_graph.nodes}
        assert statuses["manager"] == COMPLETED
        assert statuses[child1.task_key] == COMPLETED
        assert statuses[child2.task_key] == CANCELLED
        assert statuses[child3.task_key] == COMPLETED

        # WAL integrity: mutation sequences are contiguous starting from 0
        mutations = graph_repo.get_mutations(session, run_id)
        sequences = [m.sequence for m in mutations]
        assert sequences == list(range(len(sequences))), f"Mutation WAL has gaps: {sequences}"

        # Verify mutation types present
        mutation_types = [m.mutation_type for m in mutations]
        assert mutation_types.count("node.added") == 4  # parent + 3 children
        assert "node.status_changed" in mutation_types

        # Verify parent_node_id containment for children
        for node in final_graph.nodes:
            if node.task_key != "manager":
                assert node.parent_node_id == parent.id
