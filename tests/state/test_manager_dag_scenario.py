"""Full 15-step manager DAG scenario — the acceptance test for restart + invalidation.

Exercises: diamond fan-out/fan-in, 3-deep chain, independent leaf,
cancel-while-running, restart-from-CANCELLED, restart-with-completed-
downstream (deep invalidation), fan-in re-activation, cross-graph
isolation, workflow terminal detection.

Topology:

    Manager (RUNNING)
    ├── Graph 1 — diamond with fan-in:
    │   A → B → F
    │   A → C → F         (F has TWO incoming edges)
    ├── Graph 2 — chain (3-deep, for recursive invalidation):
    │   D → E → G
    └── H (independent leaf, no deps)

Runs against SQLite with per-test transaction rollback (no Docker,
no sleeps, no real Inngest).
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    EDGE_INVALIDATED,
    EDGE_PENDING,
    EDGE_SATISFIED,
    FAILED,
    PENDING,
    RUNNING,
    TERMINAL_STATUSES,
)
from ergon_core.core.runtime.execution.propagation import (
    is_workflow_complete_v2,
    on_task_completed_or_failed,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import (
    CancelTaskCommand,
    PlanSubtasksCommand,
    RestartTaskCommand,
    SubtaskSpec,
)
from ergon_core.core.runtime.services.task_management_service import TaskManagementService
from sqlmodel import Session

from tests.state.mocks import FakeInngestClient

META = MutationMeta(actor="test", reason="scenario-setup")


async def _complete(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    node_id,
) -> tuple[list, list]:
    """Simulate a worker reporting completion: write COMPLETED then propagate.

    Mirrors the production flow where the worker's on_complete callback
    calls graph_repo.update_node_status(COMPLETED) followed by
    propagation.on_task_completed_or_failed.
    """
    await repo.update_node_status(
        session,
        run_id=run_id,
        node_id=node_id,
        new_status=COMPLETED,
        meta=MutationMeta(actor="worker", reason="task completed"),
    )
    return await on_task_completed_or_failed(session, run_id, node_id, COMPLETED, graph_repo=repo)


def _assert_status(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    nodes: dict,
    expected: dict[str, str],
) -> None:
    """Bulk-assert statuses by local_key, re-reading fresh from DB."""
    for key, expected_status in expected.items():
        node = repo.get_node(session, run_id=run_id, node_id=nodes[key])
        assert node.status == expected_status, (
            f"{key}: expected {expected_status!r}, got {node.status!r}"
        )


def _edges_by_target(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    target_id,
) -> dict:
    """Map source_node_id -> edge_status for inspection in assertions."""
    return {
        edge.source_node_id: edge.status
        for edge in repo.get_incoming_edges(session, run_id=run_id, node_id=target_id)
    }


class TestManagerDAGScenario:
    """The full 15-step acceptance scenario."""

    async def test_full_15_step_scenario(self, session: Session):
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        # Manager bootstraps itself as RUNNING at level 0.
        manager = await repo.add_node(
            session,
            run_id,
            task_key="manager",
            instance_key="bench-1",
            description="manager agent",
            status=RUNNING,
            meta=META,
        )
        session.commit()

        # -- Step 1: Create all 8 children --
        # Graph 1 (diamond): A→B, A→C, B→F, C→F
        # Graph 2 (chain): D→E→G
        # H: independent leaf
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            graph1_result = await svc.plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=manager.id,
                    subtasks=[
                        SubtaskSpec(local_key="A", description="diamond root"),
                        SubtaskSpec(local_key="B", description="left arm", depends_on=["A"]),
                        SubtaskSpec(local_key="C", description="right arm", depends_on=["A"]),
                        SubtaskSpec(local_key="F", description="join", depends_on=["B", "C"]),
                    ],
                ),
            )
            graph2_result = await svc.plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=manager.id,
                    subtasks=[
                        SubtaskSpec(local_key="D", description="chain head"),
                        SubtaskSpec(local_key="E", description="chain mid", depends_on=["D"]),
                        SubtaskSpec(local_key="G", description="chain tail", depends_on=["E"]),
                    ],
                ),
            )
            leaf_result = await svc.plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=manager.id,
                    subtasks=[
                        SubtaskSpec(local_key="H", description="independent leaf"),
                    ],
                ),
            )

        nodes = {**graph1_result.nodes, **graph2_result.nodes, **leaf_result.nodes}
        assert len(nodes) == 8

        # Roots (A, D, H) have no deps; B, C, E, F, G are blocked.
        _assert_status(
            repo,
            session,
            run_id,
            nodes,
            {k: PENDING for k in ("A", "B", "C", "F", "D", "E", "G", "H")},
        )

        # -- Step 2: A completes → B, C become READY (PENDING with deps satisfied). F stays blocked. --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            newly_ready, _ = await _complete(repo, session, run_id, nodes["A"])

        assert set(newly_ready) == {nodes["B"], nodes["C"]}
        _assert_status(
            repo, session, run_id, nodes, {"A": COMPLETED, "B": PENDING, "C": PENDING, "F": PENDING}
        )

        # -- Step 3: B completes → F still blocked (C not done). --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            newly_ready, _ = await _complete(repo, session, run_id, nodes["B"])

        assert nodes["F"] not in newly_ready
        # F's incoming edges: B→F SATISFIED, C→F still PENDING.
        f_edges = _edges_by_target(repo, session, run_id, nodes["F"])
        assert f_edges[nodes["B"]] == EDGE_SATISFIED
        assert f_edges[nodes["C"]] == EDGE_PENDING

        # -- Step 4: C completes → F unblocks (all deps COMPLETED). --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            newly_ready, _ = await _complete(repo, session, run_id, nodes["C"])
        assert nodes["F"] in newly_ready
        _assert_status(repo, session, run_id, nodes, {"F": PENDING, "C": COMPLETED})

        # -- Step 5: F completes → Graph 1 done. --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            await _complete(repo, session, run_id, nodes["F"])
        _assert_status(
            repo,
            session,
            run_id,
            nodes,
            {"A": COMPLETED, "B": COMPLETED, "C": COMPLETED, "F": COMPLETED},
        )

        # -- Step 6: D completes → E ready. G blocked. --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            newly_ready, _ = await _complete(repo, session, run_id, nodes["D"])
        assert nodes["E"] in newly_ready
        assert nodes["G"] not in newly_ready
        _assert_status(repo, session, run_id, nodes, {"D": COMPLETED, "E": PENDING, "G": PENDING})

        # -- Step 7: E starts running --
        await repo.update_node_status(
            session,
            run_id=run_id,
            node_id=nodes["E"],
            new_status=RUNNING,
            meta=MutationMeta(actor="worker", reason="picked up"),
        )
        session.commit()

        # -- Step 8: Manager cancels E (while RUNNING). --
        # G stays PENDING (managed subtask no-cascade). E→G edge INVALIDATED.
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=nodes["E"]),
            )
            # The on_task_completed_or_failed call is what invalidates
            # outgoing edges on a failure/cancel — mirror the engine.
            await on_task_completed_or_failed(
                session, run_id, nodes["E"], CANCELLED, graph_repo=repo
            )

        _assert_status(repo, session, run_id, nodes, {"E": CANCELLED, "G": PENDING})
        g_edges = _edges_by_target(repo, session, run_id, nodes["G"])
        assert g_edges[nodes["E"]] == EDGE_INVALIDATED

        # -- Step 9: Manager restarts E (CANCELLED → PENDING). Edge E→G reset. --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = await svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=nodes["E"]),
            )
        assert result.old_status == CANCELLED
        _assert_status(repo, session, run_id, nodes, {"E": PENDING})
        # task/ready emitted for E.
        ready_events = fake.events_by_name("task/ready")
        assert any(evt.data["node_id"] == str(nodes["E"]) for evt in ready_events)
        # E→G edge reset to PENDING.
        g_edges = _edges_by_target(repo, session, run_id, nodes["G"])
        assert g_edges[nodes["E"]] == EDGE_PENDING

        # -- Step 10: E completes → G ready. --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            newly_ready, _ = await _complete(repo, session, run_id, nodes["E"])
        assert nodes["G"] in newly_ready
        _assert_status(repo, session, run_id, nodes, {"E": COMPLETED, "G": PENDING})

        # -- Step 11: G completes → Graph 2 done. --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            await _complete(repo, session, run_id, nodes["G"])
        _assert_status(
            repo, session, run_id, nodes, {"D": COMPLETED, "E": COMPLETED, "G": COMPLETED}
        )

        # -- Step 12: Manager restarts B (both B and F were COMPLETED). --
        # F is invalidated: CANCELLED + B→F and C→F reset to EDGE_PENDING.
        # G unaffected (different graph).
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            restart_result = await svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=nodes["B"]),
            )

        assert nodes["F"] in restart_result.invalidated_node_ids
        _assert_status(repo, session, run_id, nodes, {"B": PENDING, "F": CANCELLED})

        # Both B→F and C→F edges reset to EDGE_PENDING.
        f_edges = _edges_by_target(repo, session, run_id, nodes["F"])
        assert f_edges[nodes["B"]] == EDGE_PENDING
        assert f_edges[nodes["C"]] == EDGE_PENDING

        # Cross-graph isolation: Graph 2 untouched.
        _assert_status(
            repo, session, run_id, nodes, {"D": COMPLETED, "E": COMPLETED, "G": COMPLETED}
        )

        # -- Step 13: B completes again → F re-activates (fan-in re-activation). --
        # C is still COMPLETED → all F's deps satisfied → F becomes PENDING.
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            newly_ready, _ = await _complete(repo, session, run_id, nodes["B"])

        assert nodes["F"] in newly_ready
        _assert_status(repo, session, run_id, nodes, {"B": COMPLETED, "F": PENDING})

        # -- Step 14: F completes again → Graph 1 re-done. --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            await _complete(repo, session, run_id, nodes["F"])
        _assert_status(repo, session, run_id, nodes, {"F": COMPLETED})

        # -- Step 15: H completes, manager completes. All terminal, zero FAILED. --
        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            await _complete(repo, session, run_id, nodes["H"])

        await repo.update_node_status(
            session,
            run_id=run_id,
            node_id=manager.id,
            new_status=COMPLETED,
            meta=MutationMeta(actor="manager", reason="all children terminal"),
        )
        session.commit()

        # -- Final assertions --
        graph = repo.get_graph(session, run_id)
        assert len(graph.nodes) == 9  # manager + 8 children

        # Every node terminal, zero FAILED.
        statuses = {n.task_key: n.status for n in graph.nodes}
        for key, status in statuses.items():
            assert status in TERMINAL_STATUSES, f"{key} not terminal: {status}"
            assert status != FAILED, f"{key} unexpectedly FAILED"

        # Workflow is COMPLETED (all terminal, no FAILED).
        assert is_workflow_complete_v2(session, run_id)

        # WAL integrity: mutation sequence numbers are contiguous from 0.
        mutations = repo.get_mutations(session, run_id)
        assert [m.sequence for m in mutations] == list(range(len(mutations)))

        # Key mutation types present.
        types = [m.mutation_type for m in mutations]
        assert types.count("node.added") == 9  # manager + 8 children
        assert types.count("edge.added") == 6  # diamond: 4, chain: 2
        assert "node.status_changed" in types
        assert "edge.status_changed" in types
