"""TaskManagementService unit tests — subtask lifecycle.

Tests run against the shared SQLite session fixture with per-test rollback.
Graph nodes are created directly via WorkflowGraphRepository.
"""

from unittest.mock import patch
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
    TaskRunningError,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import (
    AddSubtaskCommand,
    CancelTaskCommand,
    RefineTaskCommand,
)
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)
from sqlmodel import Session

from tests.state.mocks import FakeInngestClient

META = MutationMeta(actor="test", reason="test-setup")


async def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    key: str,
    *,
    status: str = PENDING,
    instance_key: str = "inst-0",
    parent_node_id=None,
    level: int = 0,
):
    """Helper to create a graph node for test setup."""
    return await repo.add_node(
        session,
        run_id,
        task_key=key,
        instance_key=instance_key,
        description=f"node {key}",
        status=status,
        parent_node_id=parent_node_id,
        level=level,
        meta=META,
    )


class TestAddSubtask:
    """Tests for add_subtask — the primary subtask creation path."""

    async def test_creates_node_under_parent(self, session: Session):
        """add_subtask creates a child node with correct parent linkage."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager", instance_key="bench-1")

        result = await svc.add_subtask(
            session,
            AddSubtaskCommand(
                run_id=run_id,
                parent_node_id=parent.id,
                description="research quantum computing",
                worker_binding_key="researcher",
            ),
        )

        child = repo.get_node(session, run_id=run_id, node_id=result.node_id)
        assert child.description == "research quantum computing"
        assert child.assigned_worker_key == "researcher"
        assert child.status == PENDING
        assert child.parent_node_id == parent.id
        assert child.level == 1

    async def test_inherits_instance_key_from_parent(self, session: Session):
        """Subtask inherits instance_key from parent for benchmark cohort tracking."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager", instance_key="bench-42")

        result = await svc.add_subtask(
            session,
            AddSubtaskCommand(
                run_id=run_id,
                parent_node_id=parent.id,
                description="child task",
                worker_binding_key="worker-a",
            ),
        )

        child = repo.get_node(session, run_id=run_id, node_id=result.node_id)
        assert child.instance_key == "bench-42"

    async def test_generates_dynamic_task_key(self, session: Session):
        """Task key is prefixed with 'dynamic:' and has 8-char hex suffix."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager")

        result = await svc.add_subtask(
            session,
            AddSubtaskCommand(
                run_id=run_id,
                parent_node_id=parent.id,
                description="dynamic child",
                worker_binding_key="w",
            ),
        )

        assert result.task_key.startswith("dynamic:")
        assert len(result.task_key) == len("dynamic:") + 8

    async def test_wires_dependency_edges(self, session: Session):
        """depends_on creates edges from dependency nodes to the new subtask."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager")
        dep_node = await _add_node(repo, session, run_id, "dep", parent_node_id=parent.id, level=1)

        result = await svc.add_subtask(
            session,
            AddSubtaskCommand(
                run_id=run_id,
                parent_node_id=parent.id,
                description="depends on dep",
                worker_binding_key="w",
                depends_on=[dep_node.id],
            ),
        )

        edges = repo.get_incoming_edges(session, run_id=run_id, node_id=result.node_id)
        assert len(edges) == 1
        assert edges[0].source_node_id == dep_node.id

    async def test_mutations_logged(self, session: Session):
        """Both node.added and any edge.added mutations appear in the WAL."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager")
        seq_before = len(repo.get_mutations(session, run_id))

        await svc.add_subtask(
            session,
            AddSubtaskCommand(
                run_id=run_id,
                parent_node_id=parent.id,
                description="child",
                worker_binding_key="w",
            ),
        )

        mutations = repo.get_mutations(session, run_id)
        new_mutations = mutations[seq_before:]

        types = [m.mutation_type for m in new_mutations]
        assert "node.added" in types

        for m in new_mutations:
            assert m.actor == "manager-worker"


class TestCancelTask:
    """Tests for cancel_task — manager-initiated cancellation."""

    async def test_cancels_pending_node(self, session: Session):
        """cancel_task transitions a pending node to CANCELLED."""
        fake_inngest = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "target", status=PENDING)

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            result = await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=node.id),
            )

        assert result.old_status == PENDING
        assert result.cascaded_count == 0

        updated = repo.get_node(session, run_id=run_id, node_id=node.id)
        assert updated.status == CANCELLED

    async def test_cancels_running_node(self, session: Session):
        """cancel_task works on running nodes too."""
        fake_inngest = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "target", status=RUNNING)

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            result = await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=node.id),
            )

        assert result.old_status == RUNNING

    async def test_emits_cancelled_event(self, session: Session):
        """cancel_task emits a task/cancelled Inngest event."""
        fake_inngest = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "target", status=PENDING)

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=node.id),
            )

        cancelled_events = fake_inngest.events_by_name("task/cancelled")
        assert len(cancelled_events) == 1
        assert cancelled_events[0].data["node_id"] == str(node.id)
        assert cancelled_events[0].data["cause"] == "manager_decision"

    async def test_on_completed_node_raises(self, session: Session):
        """cancel_task raises TaskAlreadyTerminalError on completed nodes."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "done", status=COMPLETED)

        with pytest.raises(TaskAlreadyTerminalError) as exc_info:
            await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=node.id),
            )
        assert exc_info.value.node_id == node.id
        assert exc_info.value.current_status == COMPLETED

    async def test_on_failed_node_raises(self, session: Session):
        """cancel_task raises on already-failed nodes."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "failed", status=FAILED)

        with pytest.raises(TaskAlreadyTerminalError):
            await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=node.id),
            )

    async def test_on_cancelled_node_raises(self, session: Session):
        """cancel_task raises on already-cancelled nodes."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "gone", status=CANCELLED)

        with pytest.raises(TaskAlreadyTerminalError):
            await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=node.id),
            )

    async def test_counts_non_terminal_descendants(self, session: Session):
        """cascaded_count reflects non-terminal children of the cancelled node."""
        fake_inngest = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "parent", status=RUNNING)
        await _add_node(
            repo,
            session,
            run_id,
            "child-a",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )
        await _add_node(
            repo,
            session,
            run_id,
            "child-b",
            status=RUNNING,
            parent_node_id=parent.id,
            level=1,
        )
        await _add_node(
            repo,
            session,
            run_id,
            "child-c",
            status=COMPLETED,
            parent_node_id=parent.id,
            level=1,
        )

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            result = await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=parent.id),
            )

        # child-a (pending) + child-b (running) = 2 non-terminal
        assert result.cascaded_count == 2

    async def test_mutation_logged(self, session: Session):
        """cancel_task logs a node.status_changed mutation."""
        fake_inngest = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "target", status=PENDING)
        seq_before = len(repo.get_mutations(session, run_id))

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            await svc.cancel_task(
                session,
                CancelTaskCommand(run_id=run_id, node_id=node.id),
            )

        mutations = repo.get_mutations(session, run_id)
        new_mutations = mutations[seq_before:]

        assert any(m.mutation_type == "node.status_changed" for m in new_mutations)
        status_mut = next(m for m in new_mutations if m.mutation_type == "node.status_changed")
        assert status_mut.new_value.status == CANCELLED  # type: ignore[union-attr]


class TestRefineTask:
    """Tests for refine_task — updating description on pending nodes."""

    async def test_updates_description(self, session: Session):
        """refine_task updates the node description and returns old/new."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "target", status=PENDING)

        result = await svc.refine_task(
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

    async def test_on_running_raises(self, session: Session):
        """refine_task raises TaskRunningError on RUNNING nodes only."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "busy", status=RUNNING)

        with pytest.raises(TaskRunningError) as exc_info:
            await svc.refine_task(
                session,
                RefineTaskCommand(
                    run_id=run_id,
                    node_id=node.id,
                    new_description="too late",
                ),
            )
        assert exc_info.value.node_id == node.id
        assert exc_info.value.current_status == RUNNING

    @pytest.mark.parametrize("status", [COMPLETED, FAILED, CANCELLED])
    async def test_on_terminal_allowed(self, session: Session, status: str):
        """refine_task now accepts COMPLETED / FAILED / CANCELLED nodes.

        Supports the edit-then-rerun flow: the manager can update the
        description on a terminal node before calling restart_task.
        """
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, f"node-{status}", status=status)

        result = await svc.refine_task(
            session,
            RefineTaskCommand(
                run_id=run_id,
                node_id=node.id,
                new_description=f"refined while {status}",
            ),
        )

        assert result.new_description == f"refined while {status}"

        updated = repo.get_node(session, run_id=run_id, node_id=node.id)
        assert updated.description == f"refined while {status}"
        # Status must be unchanged — refine does not transition.
        assert updated.status == status

    async def test_mutation_logged(self, session: Session):
        """refine_task logs a node.field_changed mutation."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = await _add_node(repo, session, run_id, "target", status=PENDING)
        seq_before = len(repo.get_mutations(session, run_id))

        await svc.refine_task(
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
