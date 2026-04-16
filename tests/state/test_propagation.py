"""DAG propagation invariant tests.

Tests the functions in propagation.py directly (they take Session),
bypassing the thin service wrappers. All state is verified via
RunGraphNode.status and RunGraphMutation rows.
"""

from uuid import uuid4

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.runtime.execution.propagation import (
    get_initial_ready_tasks,
    is_workflow_complete,
    is_workflow_failed,
    mark_task_completed,
    mark_task_failed,
    on_task_completed,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_lookup import GraphNodeLookup
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from sqlmodel import Session, select

from tests.state.factories import (
    seed_chain,
    seed_diamond,
    seed_flat_tasks,
    seed_run,
)


def _init_graph(session: Session, run_id, def_id):
    """Initialize the graph and return (graph_repo, graph_lookup)."""
    repo = WorkflowGraphRepository()
    repo.initialize_from_definition(
        session,
        run_id,
        def_id,
        initial_node_status=TaskExecutionStatus.PENDING,
        initial_edge_status="pending",
        meta=MutationMeta(actor="test"),
    )
    session.commit()
    lookup = GraphNodeLookup(session, run_id)
    return repo, lookup


class TestDiamondFanIn:
    def test_diamond_fan_in_waits_for_all_deps(self, session: Session):
        """D should only become ready when BOTH B and C are completed."""
        def_id, _, task_ids, _ = seed_diamond(session)
        a, b, c, d = task_ids
        run_id = seed_run(session, def_id)
        repo, lookup = _init_graph(session, run_id, def_id)

        ready = get_initial_ready_tasks(
            session,
            run_id,
            def_id,
            graph_repo=repo,
            graph_lookup=lookup,
        )
        assert set(ready) == {a}

        after_a = on_task_completed(
            session,
            run_id,
            def_id,
            a,
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        assert set(after_a) == {b, c}

        after_b = on_task_completed(
            session,
            run_id,
            def_id,
            b,
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        assert d not in after_b

        after_c = on_task_completed(
            session,
            run_id,
            def_id,
            c,
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        assert d in after_c


class TestChainPropagation:
    def test_chain_propagation_step_by_step(self, session: Session):
        def_id, _, task_ids, _ = seed_chain(session, 3)
        a, b, c = task_ids
        run_id = seed_run(session, def_id)
        repo, lookup = _init_graph(session, run_id, def_id)

        ready = get_initial_ready_tasks(
            session,
            run_id,
            def_id,
            graph_repo=repo,
            graph_lookup=lookup,
        )
        assert set(ready) == {a}

        after_a = on_task_completed(
            session,
            run_id,
            def_id,
            a,
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        assert set(after_a) == {b}

        after_b = on_task_completed(
            session,
            run_id,
            def_id,
            b,
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        assert set(after_b) == {c}

        after_c = on_task_completed(
            session,
            run_id,
            def_id,
            c,
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        assert after_c == []

        assert is_workflow_complete(session, run_id, def_id)


class TestFlatTasks:
    def test_flat_tasks_all_initially_ready(self, session: Session):
        def_id, _, task_ids = seed_flat_tasks(session, 3)
        run_id = seed_run(session, def_id)
        repo, lookup = _init_graph(session, run_id, def_id)

        ready = get_initial_ready_tasks(
            session,
            run_id,
            def_id,
            graph_repo=repo,
            graph_lookup=lookup,
        )
        assert set(ready) == set(task_ids)


class TestFailureDetection:
    def test_is_workflow_failed_when_any_task_fails(self, session: Session):
        def_id, _, task_ids = seed_flat_tasks(session, 3)
        run_id = seed_run(session, def_id)
        repo, lookup = _init_graph(session, run_id, def_id)

        mark_task_completed(
            session,
            run_id,
            task_ids[0],
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        mark_task_failed(
            session,
            run_id,
            task_ids[1],
            "boom",
            graph_repo=repo,
            graph_lookup=lookup,
        )
        session.flush()

        assert is_workflow_failed(session, run_id, def_id)
        assert not is_workflow_complete(session, run_id, def_id)


class TestCompletionRequiresAll:
    def test_is_workflow_complete_requires_all_tasks(self, session: Session):
        def_id, _, task_ids = seed_flat_tasks(session, 3)
        run_id = seed_run(session, def_id)
        repo, lookup = _init_graph(session, run_id, def_id)

        mark_task_completed(
            session,
            run_id,
            task_ids[0],
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        mark_task_completed(
            session,
            run_id,
            task_ids[1],
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        session.flush()

        assert not is_workflow_complete(session, run_id, def_id)


class TestGraphStateVerification:
    """Verify that state is written to RunGraphNode and RunGraphMutation,
    not to RunTaskStateEvent."""

    def test_graph_nodes_have_correct_status(self, session: Session):
        def_id, _, task_ids, _ = seed_chain(session, 2)
        a, b = task_ids
        run_id = seed_run(session, def_id)
        repo, lookup = _init_graph(session, run_id, def_id)

        on_task_completed(
            session,
            run_id,
            def_id,
            a,
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )

        node_a = session.exec(
            select(RunGraphNode).where(
                RunGraphNode.run_id == run_id,
                RunGraphNode.definition_task_id == a,
            )
        ).first()
        assert node_a is not None
        assert node_a.status == TaskExecutionStatus.COMPLETED

        node_b = session.exec(
            select(RunGraphNode).where(
                RunGraphNode.run_id == run_id,
                RunGraphNode.definition_task_id == b,
            )
        ).first()
        assert node_b is not None
        assert node_b.status == TaskExecutionStatus.PENDING

    def test_mutations_are_logged(self, session: Session):
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        repo, lookup = _init_graph(session, run_id, def_id)

        mark_task_completed(
            session,
            run_id,
            task_ids[0],
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )
        session.flush()

        mutations = list(
            session.exec(
                select(RunGraphMutation).where(
                    RunGraphMutation.run_id == run_id,
                    RunGraphMutation.mutation_type == "node.status_changed",
                )
            ).all()
        )
        assert len(mutations) >= 1
        last = mutations[-1]
        assert last.new_value["status"] == TaskExecutionStatus.COMPLETED

    def test_edge_status_updated_on_dependency_resolution(self, session: Session):
        def_id, _, task_ids, _ = seed_chain(session, 2)
        a, b = task_ids
        run_id = seed_run(session, def_id)
        repo, lookup = _init_graph(session, run_id, def_id)

        on_task_completed(
            session,
            run_id,
            def_id,
            a,
            uuid4(),
            graph_repo=repo,
            graph_lookup=lookup,
        )

        from ergon_core.core.persistence.graph.models import RunGraphEdge

        edges = list(session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all())
        assert len(edges) == 1
        assert edges[0].status == "satisfied"
