"""TaskManagementService unit tests.

Tests run against the shared SQLite session fixture with per-test rollback.
Graph nodes are created directly via WorkflowGraphRepository.
"""

from uuid import uuid4

import pytest
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    FAILED,
    PENDING,
    RUNNING,
)
from ergon_core.core.runtime.errors.delegation_errors import (
    TaskAlreadyTerminalError,
    TaskNotPendingError,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import (
    AbandonTaskCommand,
    AddTaskCommand,
    RefineTaskCommand,
)
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)
from sqlmodel import Session

META = MutationMeta(actor="test", reason="test-setup")


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


class TestAddTask:
    def test_creates_node_and_edge(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()
        definition_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager", instance_key="bench-1")

        result = svc.add_task(
            session,
            AddTaskCommand(
                run_id=run_id,
                definition_id=definition_id,
                parent_node_id=parent.id,
                description="research quantum computing",
                worker_binding_key="researcher",
            ),
        )

        child = repo.get_node(session, run_id=run_id, node_id=result.node_id)
        assert child.description == "research quantum computing"
        assert child.assigned_worker_key == "researcher"
        assert child.status == PENDING

        edge = repo.get_edge(session, run_id=run_id, edge_id=result.edge_id)
        assert edge.source_node_id == parent.id
        assert edge.target_node_id == result.node_id

    def test_inherits_instance_key_from_parent(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager", instance_key="bench-42")

        result = svc.add_task(
            session,
            AddTaskCommand(
                run_id=run_id,
                definition_id=uuid4(),
                parent_node_id=parent.id,
                description="child task",
                worker_binding_key="worker-a",
            ),
        )

        child = repo.get_node(session, run_id=run_id, node_id=result.node_id)
        assert child.instance_key == "bench-42"

    def test_generates_dynamic_task_key(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager")

        result = svc.add_task(
            session,
            AddTaskCommand(
                run_id=run_id,
                definition_id=uuid4(),
                parent_node_id=parent.id,
                description="dynamic child",
                worker_binding_key="w",
            ),
        )

        assert result.task_key.startswith("dynamic:")
        assert len(result.task_key) == len("dynamic:") + 8

    def test_mutations_logged(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager")
        seq_before = len(repo.get_mutations(session, run_id))

        svc.add_task(
            session,
            AddTaskCommand(
                run_id=run_id,
                definition_id=uuid4(),
                parent_node_id=parent.id,
                description="child",
                worker_binding_key="w",
            ),
        )

        mutations = repo.get_mutations(session, run_id)
        new_mutations = mutations[seq_before:]

        types = [m.mutation_type for m in new_mutations]
        assert "node.added" in types
        assert "edge.added" in types

        for m in new_mutations:
            assert m.actor == "manager-worker"


class TestAbandonTask:
    def test_transitions_pending_to_abandoned(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=PENDING)

        result = svc.abandon_task(
            session,
            AbandonTaskCommand(run_id=run_id, node_id=node.id),
        )

        assert result.previous_status == PENDING
        assert result.new_status == CANCELLED

        updated = repo.get_node(session, run_id=run_id, node_id=node.id)
        assert updated.status == CANCELLED

    def test_transitions_running_to_abandoned(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=RUNNING)

        result = svc.abandon_task(
            session,
            AbandonTaskCommand(run_id=run_id, node_id=node.id),
        )

        assert result.previous_status == RUNNING
        assert result.new_status == CANCELLED

    def test_on_completed_node_raises(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "done", status=COMPLETED)

        with pytest.raises(TaskAlreadyTerminalError) as exc_info:
            svc.abandon_task(
                session,
                AbandonTaskCommand(run_id=run_id, node_id=node.id),
            )
        assert exc_info.value.node_id == node.id
        assert exc_info.value.current_status == COMPLETED

    def test_on_failed_node_raises(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "failed", status=FAILED)

        with pytest.raises(TaskAlreadyTerminalError):
            svc.abandon_task(
                session,
                AbandonTaskCommand(run_id=run_id, node_id=node.id),
            )

    def test_on_abandoned_node_raises(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "gone", status=CANCELLED)

        with pytest.raises(TaskAlreadyTerminalError):
            svc.abandon_task(
                session,
                AbandonTaskCommand(run_id=run_id, node_id=node.id),
            )

    def test_mutation_logged(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=PENDING)
        seq_before = len(repo.get_mutations(session, run_id))

        svc.abandon_task(
            session,
            AbandonTaskCommand(run_id=run_id, node_id=node.id),
        )

        mutations = repo.get_mutations(session, run_id)
        new_mutations = mutations[seq_before:]

        assert any(m.mutation_type == "node.status_changed" for m in new_mutations)
        status_mut = next(m for m in new_mutations if m.mutation_type == "node.status_changed")
        assert status_mut.new_value.status == CANCELLED  # type: ignore[union-attr]


class TestRefineTask:
    def test_updates_description(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=PENDING)

        result = svc.refine_task(
            session,
            RefineTaskCommand(
                run_id=run_id,
                node_id=node.id,
                new_description="improved description",
            ),
        )

        assert result.old_description == "node target"
        assert result.new_description == "improved description"

        updated = repo.get_node(session, run_id=run_id, node_id=node.id)
        assert updated.description == "improved description"

    def test_on_non_pending_raises(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "busy", status=RUNNING)

        with pytest.raises(TaskNotPendingError) as exc_info:
            svc.refine_task(
                session,
                RefineTaskCommand(
                    run_id=run_id,
                    node_id=node.id,
                    new_description="too late",
                ),
            )
        assert exc_info.value.node_id == node.id
        assert exc_info.value.current_status == RUNNING

    def test_mutation_logged(self, session: Session):
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=PENDING)
        seq_before = len(repo.get_mutations(session, run_id))

        svc.refine_task(
            session,
            RefineTaskCommand(
                run_id=run_id,
                node_id=node.id,
                new_description="refined",
            ),
        )

        mutations = repo.get_mutations(session, run_id)
        new_mutations = mutations[seq_before:]

        assert any(m.mutation_type == "node.field_changed" for m in new_mutations)
        field_mut = next(m for m in new_mutations if m.mutation_type == "node.field_changed")
        assert field_mut.new_value.field == "description"  # type: ignore[union-attr]
        assert field_mut.new_value.value == "refined"  # type: ignore[union-attr]
