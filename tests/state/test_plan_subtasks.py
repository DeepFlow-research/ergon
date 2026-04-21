"""plan_subtasks validation and integration tests.

Exercises the batch subtask creation path including dependency
validation (duplicates, unknown refs, cycles) and root dispatch.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from ergon_core.core.persistence.graph.status_conventions import PENDING
from ergon_core.core.runtime.errors.delegation_errors import (
    CycleDetectedError,
    DuplicateLocalKeyError,
    UnknownLocalKeyError,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import (
    PlanSubtasksCommand,
    SubtaskSpec,
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
):
    """Helper to create a graph node for test setup."""
    return await repo.add_node(
        session,
        run_id,
        task_key=key,
        instance_key=instance_key,
        description=f"node {key}",
        status=status,
        meta=META,
    )


class TestPlanSubtasksValidation:
    """Validation-only tests — no DB interaction needed for these."""

    async def test_duplicate_local_key_raises(self, session: Session):
        """Two specs with the same local_key are rejected."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()
        parent = await _add_node(repo, session, run_id, "manager")

        with pytest.raises(DuplicateLocalKeyError) as exc_info:
            await svc.plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    subtasks=[
                        SubtaskSpec(local_key="a", description="first"),
                        SubtaskSpec(local_key="a", description="duplicate"),
                    ],
                ),
            )
        assert exc_info.value.key == "a"

    async def test_unknown_depends_on_raises(self, session: Session):
        """depends_on referencing a key not in the plan is rejected."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()
        parent = await _add_node(repo, session, run_id, "manager")

        with pytest.raises(UnknownLocalKeyError) as exc_info:
            await svc.plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    subtasks=[
                        SubtaskSpec(local_key="a", description="ok"),
                        SubtaskSpec(
                            local_key="b",
                            description="bad dep",
                            depends_on=["nonexistent"],
                        ),
                    ],
                ),
            )
        assert "nonexistent" in exc_info.value.unknown

    async def test_cycle_raises(self, session: Session):
        """A -> B -> A cycle is detected and rejected."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()
        parent = await _add_node(repo, session, run_id, "manager")

        with pytest.raises(CycleDetectedError) as exc_info:
            await svc.plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    subtasks=[
                        SubtaskSpec(local_key="a", description="first", depends_on=["b"]),
                        SubtaskSpec(local_key="b", description="second", depends_on=["a"]),
                    ],
                ),
            )
        assert len(exc_info.value.remaining_keys) == 2


class TestPlanSubtasksIntegration:
    """Integration tests that verify nodes and edges are created correctly."""

    async def test_creates_nodes_and_edges(self, session: Session):
        """plan_subtasks creates all nodes with correct parent linkage and dep edges."""
        fake_inngest = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()
        parent = await _add_node(repo, session, run_id, "manager", instance_key="bench-1")

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            result = await svc.plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    subtasks=[
                        SubtaskSpec(local_key="research", description="do research"),
                        SubtaskSpec(
                            local_key="synthesize",
                            description="synthesize results",
                            depends_on=["research"],
                        ),
                    ],
                ),
            )

        assert set(result.nodes.keys()) == {"research", "synthesize"}
        assert result.roots == ["research"]

        # Verify nodes exist with correct parent
        for key, nid in result.nodes.items():
            node = repo.get_node(session, run_id=run_id, node_id=nid)
            assert node.parent_node_id == parent.id
            assert node.level == 1
            assert node.instance_key == "bench-1"

        # Verify dependency edge: research -> synthesize
        edges = repo.get_incoming_edges(session, run_id=run_id, node_id=result.nodes["synthesize"])
        assert len(edges) == 1
        assert edges[0].source_node_id == result.nodes["research"]

    async def test_dispatches_root_tasks(self, session: Session):
        """Roots (tasks with no depends_on) get task/ready events dispatched."""
        fake_inngest = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()
        parent = await _add_node(repo, session, run_id, "manager")

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            result = await svc.plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    subtasks=[
                        SubtaskSpec(local_key="a", description="root a"),
                        SubtaskSpec(local_key="b", description="root b"),
                        SubtaskSpec(
                            local_key="c",
                            description="depends on a and b",
                            depends_on=["a", "b"],
                        ),
                    ],
                ),
            )

        assert sorted(result.roots) == ["a", "b"]

        ready_events = fake_inngest.events_by_name("task/ready")
        assert len(ready_events) == 2

        dispatched_node_ids = {e.data["node_id"] for e in ready_events}
        assert str(result.nodes["a"]) in dispatched_node_ids
        assert str(result.nodes["b"]) in dispatched_node_ids

    async def test_empty_plan_is_noop(self, session: Session):
        """An empty subtasks list creates no nodes."""
        fake_inngest = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()
        parent = await _add_node(repo, session, run_id, "manager")

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake_inngest,
        ):
            result = await svc.plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    subtasks=[],
                ),
            )

        assert result.nodes == {}
        assert result.roots == []
        assert len(fake_inngest.events_by_name("task/ready")) == 0
