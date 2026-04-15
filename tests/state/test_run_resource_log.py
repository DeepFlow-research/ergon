"""Append-only RunResource log: schema + query semantics.

Tests run against the shared SQLite session fixture with per-test rollback.
"""

from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunResourceKind,
    RunTaskExecution,
)
from ergon_core.core.utils import utcnow as _utcnow


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _patch_get_session(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    """Monkeypatch ``get_session`` so query methods use the test transaction."""

    @contextmanager
    def _test_session():
        yield session

    monkeypatch.setattr(
        "ergon_core.core.persistence.queries.get_session",
        _test_session,
    )


def _seed_run(session: Session) -> RunRecord:
    run = RunRecord(
        id=uuid4(),
        experiment_definition_id=uuid4(),
        status=RunStatus.PENDING,
    )
    session.add(run)
    session.flush()
    return run


def _seed_execution(
    session: Session,
    run: RunRecord,
    *,
    node_id=None,
) -> RunTaskExecution:
    exe = RunTaskExecution(
        id=uuid4(),
        run_id=run.id,
        status=TaskExecutionStatus.RUNNING,
        node_id=node_id,
    )
    session.add(exe)
    session.flush()
    return exe


# ---------------------------------------------------------------------------
# append() inserts, never updates
# ---------------------------------------------------------------------------


class TestAppend:
    def test_two_appends_same_path_yield_two_rows(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        r1 = queries.resources.append(
            run_id=run.id,
            task_execution_id=exe.id,
            kind=RunResourceKind.REPORT,
            name="draft.md",
            mime_type="text/markdown",
            file_path="/blobs/aaa",
            size_bytes=100,
            error=None,
            content_hash="hash_a",
        )
        r2 = queries.resources.append(
            run_id=run.id,
            task_execution_id=exe.id,
            kind=RunResourceKind.REPORT,
            name="draft.md",
            mime_type="text/markdown",
            file_path="/blobs/aaa",
            size_bytes=120,
            error=None,
            content_hash="hash_b",
        )

        assert r1.id != r2.id
        # Both rows survive (no upsert)
        all_rows = queries.resources.list_by_execution(exe.id)
        assert len(all_rows) == 2

    def test_append_stores_error_and_hash(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        row = queries.resources.append(
            run_id=run.id,
            task_execution_id=exe.id,
            kind=RunResourceKind.NOTE,
            name="err.txt",
            mime_type="text/plain",
            file_path="/blobs/bbb",
            size_bytes=0,
            error="timeout",
            content_hash="hash_err",
        )

        assert row.error == "timeout"
        assert row.content_hash == "hash_err"


# ---------------------------------------------------------------------------
# latest_by_path
# ---------------------------------------------------------------------------


class TestLatestByPath:
    def test_returns_most_recent(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        now = _utcnow()
        older = RunResource(
            run_id=run.id,
            task_execution_id=exe.id,
            kind="report",
            name="draft.md",
            mime_type="text/markdown",
            file_path="/workspace/draft.md",
            size_bytes=100,
            content_hash="old_hash",
            created_at=now - timedelta(seconds=10),
        )
        newer = RunResource(
            run_id=run.id,
            task_execution_id=exe.id,
            kind="report",
            name="draft.md",
            mime_type="text/markdown",
            file_path="/workspace/draft.md",
            size_bytes=200,
            content_hash="new_hash",
            created_at=now,
        )
        session.add(older)
        session.add(newer)
        session.flush()

        result = queries.resources.latest_by_path(
            task_execution_id=exe.id,
            file_path="/workspace/draft.md",
        )
        assert result is not None
        assert result.content_hash == "new_hash"

    def test_returns_none_when_missing(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        result = queries.resources.latest_by_path(
            task_execution_id=uuid4(),
            file_path="/nonexistent",
        )
        assert result is None


# ---------------------------------------------------------------------------
# find_by_hash
# ---------------------------------------------------------------------------


class TestFindByHash:
    def test_returns_matching_row(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        row = queries.resources.append(
            run_id=run.id,
            task_execution_id=exe.id,
            kind=RunResourceKind.ARTIFACT,
            name="data.csv",
            mime_type="text/csv",
            file_path="/blobs/ccc",
            size_bytes=500,
            error=None,
            content_hash="sha256_abc",
        )

        found = queries.resources.find_by_hash(
            task_execution_id=exe.id,
            content_hash="sha256_abc",
        )
        assert found is not None
        assert found.id == row.id

    def test_returns_none_when_no_match(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        found = queries.resources.find_by_hash(
            task_execution_id=uuid4(),
            content_hash="nonexistent",
        )
        assert found is None


# ---------------------------------------------------------------------------
# list_latest_for_execution
# ---------------------------------------------------------------------------


class TestListLatestForExecution:
    def test_one_row_per_file_path_most_recent_wins(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        now = _utcnow()
        # Two versions of draft.md
        session.add(
            RunResource(
                run_id=run.id,
                task_execution_id=exe.id,
                kind="report",
                name="draft.md",
                mime_type="text/markdown",
                file_path="/workspace/draft.md",
                size_bytes=100,
                content_hash="v1",
                created_at=now - timedelta(seconds=10),
            )
        )
        session.add(
            RunResource(
                run_id=run.id,
                task_execution_id=exe.id,
                kind="report",
                name="draft.md",
                mime_type="text/markdown",
                file_path="/workspace/draft.md",
                size_bytes=200,
                content_hash="v2",
                created_at=now,
            )
        )
        # One version of notes.txt
        session.add(
            RunResource(
                run_id=run.id,
                task_execution_id=exe.id,
                kind="note",
                name="notes.txt",
                mime_type="text/plain",
                file_path="/workspace/notes.txt",
                size_bytes=50,
                content_hash="n1",
                created_at=now,
            )
        )
        session.flush()

        results = queries.resources.list_latest_for_execution(exe.id)
        paths = {r.file_path: r.content_hash for r in results}
        assert len(results) == 2
        assert paths["/workspace/draft.md"] == "v2"
        assert paths["/workspace/notes.txt"] == "n1"


# ---------------------------------------------------------------------------
# list_children_of
# ---------------------------------------------------------------------------


class TestListChildrenOf:
    def test_returns_only_direct_children(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)

        # Build graph: parent_node -> child_node_a, child_node_b
        parent_node = RunGraphNode(
            id=uuid4(),
            run_id=run.id,
            instance_key="inst-0",
            task_key="manager",
            description="parent",
            status="running",
        )
        child_node_a = RunGraphNode(
            id=uuid4(),
            run_id=run.id,
            instance_key="inst-0",
            task_key="researcher-a",
            description="child a",
            status="running",
        )
        child_node_b = RunGraphNode(
            id=uuid4(),
            run_id=run.id,
            instance_key="inst-0",
            task_key="researcher-b",
            description="child b",
            status="running",
        )
        # Unrelated sibling node
        sibling_node = RunGraphNode(
            id=uuid4(),
            run_id=run.id,
            instance_key="inst-0",
            task_key="sibling",
            description="sibling",
            status="running",
        )
        session.add_all([parent_node, child_node_a, child_node_b, sibling_node])
        session.flush()

        # Edges: parent -> child_a, parent -> child_b
        session.add(
            RunGraphEdge(
                run_id=run.id,
                source_node_id=parent_node.id,
                target_node_id=child_node_a.id,
                status="active",
            )
        )
        session.add(
            RunGraphEdge(
                run_id=run.id,
                source_node_id=parent_node.id,
                target_node_id=child_node_b.id,
                status="active",
            )
        )
        session.flush()

        # Executions
        parent_exe = _seed_execution(session, run, node_id=parent_node.id)
        child_exe_a = _seed_execution(session, run, node_id=child_node_a.id)
        child_exe_b = _seed_execution(session, run, node_id=child_node_b.id)
        _seed_execution(session, run, node_id=sibling_node.id)  # not a child

        children = queries.task_executions.list_children_of(parent_exe.id)
        child_ids = {c.id for c in children}
        assert child_ids == {child_exe_a.id, child_exe_b.id}

    def test_returns_empty_for_leaf(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)

        leaf_node = RunGraphNode(
            id=uuid4(),
            run_id=run.id,
            instance_key="inst-0",
            task_key="leaf",
            description="leaf",
            status="running",
        )
        session.add(leaf_node)
        session.flush()

        exe = _seed_execution(session, run, node_id=leaf_node.id)
        children = queries.task_executions.list_children_of(exe.id)
        assert children == []

    def test_returns_empty_for_unknown_id(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        children = queries.task_executions.list_children_of(uuid4())
        assert children == []
