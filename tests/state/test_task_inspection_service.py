"""TaskInspectionService unit tests.

Verifies read-only subtask queries: direct children only,
deterministic order, and empty children handling.
"""

from uuid import uuid4

from ergon_core.core.persistence.graph.status_conventions import (
    COMPLETED,
    FAILED,
    PENDING,
    RUNNING,
)
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_inspection_service import (
    TaskInspectionService,
)
from ergon_core.core.utils import utcnow
from sqlmodel import Session

META = MutationMeta(actor="test", reason="test-setup")


async def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    slug: str,
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
        task_slug=slug,
        instance_key=instance_key,
        description=f"node {slug}",
        status=status,
        parent_node_id=parent_node_id,
        level=level,
        meta=META,
    )


class TestListSubtasks:
    """Tests for list_subtasks — direct children query."""

    async def test_returns_direct_children_only(self, session: Session):
        """list_subtasks returns only direct children, not grandchildren."""
        repo = WorkflowGraphRepository()
        svc = TaskInspectionService()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "parent", status=RUNNING)
        child_a = await _add_node(
            repo,
            session,
            run_id,
            "child-a",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )
        child_b = await _add_node(
            repo,
            session,
            run_id,
            "child-b",
            status=RUNNING,
            parent_node_id=parent.id,
            level=1,
        )
        # Grandchild should NOT appear
        await _add_node(
            repo,
            session,
            run_id,
            "grandchild",
            status=PENDING,
            parent_node_id=child_a.id,
            level=2,
        )

        results = svc.list_subtasks(session, run_id=run_id, parent_node_id=parent.id)

        assert len(results) == 2
        result_ids = {r.node_id for r in results}
        assert child_a.id in result_ids
        assert child_b.id in result_ids

    async def test_deterministic_order_by_task_slug(self, session: Session):
        """Results are ordered by task_slug for stable LLM references."""
        repo = WorkflowGraphRepository()
        svc = TaskInspectionService()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "parent", status=RUNNING)
        # Create in reverse order to verify sorting
        await _add_node(
            repo,
            session,
            run_id,
            "zzz-last",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )
        await _add_node(
            repo,
            session,
            run_id,
            "aaa-first",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )

        results = svc.list_subtasks(session, run_id=run_id, parent_node_id=parent.id)

        assert len(results) == 2
        assert results[0].task_slug == "aaa-first"
        assert results[1].task_slug == "zzz-last"

    async def test_empty_children(self, session: Session):
        """A parent with no children returns an empty list."""
        repo = WorkflowGraphRepository()
        svc = TaskInspectionService()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "lonely", status=RUNNING)

        results = svc.list_subtasks(session, run_id=run_id, parent_node_id=parent.id)

        assert results == []

    async def test_hydrates_output_for_completed(self, session: Session):
        """Completed subtasks include truncated output_text from execution."""
        repo = WorkflowGraphRepository()
        svc = TaskInspectionService()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "parent", status=RUNNING)
        child = await _add_node(
            repo,
            session,
            run_id,
            "done-child",
            status=COMPLETED,
            parent_node_id=parent.id,
            level=1,
        )

        # Seed an execution with output
        session.add(
            RunTaskExecution(
                run_id=run_id,
                node_id=child.id,
                status=TaskExecutionStatus.COMPLETED,
                started_at=utcnow(),
                output_text="research results here",
            )
        )
        session.flush()

        results = svc.list_subtasks(session, run_id=run_id, parent_node_id=parent.id)

        assert len(results) == 1
        assert results[0].output == "research results here"
        assert results[0].error is None

    async def test_hydrates_error_for_failed(self, session: Session):
        """Failed subtasks include error message from execution."""
        repo = WorkflowGraphRepository()
        svc = TaskInspectionService()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "parent", status=RUNNING)
        child = await _add_node(
            repo,
            session,
            run_id,
            "failed-child",
            status=FAILED,
            parent_node_id=parent.id,
            level=1,
        )

        session.add(
            RunTaskExecution(
                run_id=run_id,
                node_id=child.id,
                status=TaskExecutionStatus.FAILED,
                started_at=utcnow(),
                error_json={"message": "timeout exceeded"},
            )
        )
        session.flush()

        results = svc.list_subtasks(session, run_id=run_id, parent_node_id=parent.id)

        assert len(results) == 1
        assert results[0].error == "timeout exceeded"
        assert results[0].output is None

    async def test_includes_dependency_edges(self, session: Session):
        """depends_on reflects incoming dependency edges."""
        repo = WorkflowGraphRepository()
        svc = TaskInspectionService()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "parent", status=RUNNING)
        dep = await _add_node(
            repo,
            session,
            run_id,
            "dep-node",
            status=COMPLETED,
            parent_node_id=parent.id,
            level=1,
        )
        target = await _add_node(
            repo,
            session,
            run_id,
            "target-node",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )

        await repo.add_edge(
            session,
            run_id,
            source_node_id=dep.id,
            target_node_id=target.id,
            status="pending",
            meta=META,
        )

        results = svc.list_subtasks(session, run_id=run_id, parent_node_id=parent.id)

        target_info = next(r for r in results if r.node_id == target.id)
        assert dep.id in target_info.depends_on
