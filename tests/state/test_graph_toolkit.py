"""ResearchGraphToolkit: state tests against real SQLite DB.

Covers all six tools with run-scoping, depth limits, cycle safety, and
empty-case behaviour.  Follows the same fixture pattern as
``test_run_resource_log.py``.
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

from ergon_builtins.tools.graph_toolkit import ResearchGraphToolkit


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


def _seed_node(
    session: Session,
    run: RunRecord,
    *,
    task_key: str = "task",
) -> RunGraphNode:
    node = RunGraphNode(
        id=uuid4(),
        run_id=run.id,
        instance_key="inst-0",
        task_key=task_key,
        description=task_key,
        status="running",
    )
    session.add(node)
    session.flush()
    return node


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


def _seed_edge(
    session: Session,
    run: RunRecord,
    source_node: RunGraphNode,
    target_node: RunGraphNode,
) -> RunGraphEdge:
    edge = RunGraphEdge(
        run_id=run.id,
        source_node_id=source_node.id,
        target_node_id=target_node.id,
        status="active",
    )
    session.add(edge)
    session.flush()
    return edge


def _seed_resource(
    session: Session,
    run: RunRecord,
    exe: RunTaskExecution,
    *,
    name: str = "file.md",
    file_path: str = "/workspace/file.md",
    content_hash: str = "hash_a",
    created_at=None,
) -> RunResource:
    row = RunResource(
        run_id=run.id,
        task_execution_id=exe.id,
        kind=RunResourceKind.REPORT,
        name=name,
        mime_type="text/markdown",
        file_path=file_path,
        size_bytes=100,
        content_hash=content_hash,
        created_at=created_at or _utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def _build_toolkit(
    run: RunRecord,
    exe: RunTaskExecution,
) -> ResearchGraphToolkit:
    return ResearchGraphToolkit(run_id=run.id, task_execution_id=exe.id)


# ---------------------------------------------------------------------------
# list_my_resources
# ---------------------------------------------------------------------------


class TestListMyResources:
    @pytest.mark.asyncio
    async def test_returns_own_resources_desc_order(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        node = _seed_node(session, run, task_key="me")
        exe = _seed_execution(session, run, node_id=node.id)

        now = _utcnow()
        r_old = _seed_resource(
            session,
            run,
            exe,
            name="old.md",
            file_path="/workspace/old.md",
            content_hash="old",
            created_at=now - timedelta(seconds=10),
        )
        r_new = _seed_resource(
            session,
            run,
            exe,
            name="new.md",
            file_path="/workspace/new.md",
            content_hash="new",
            created_at=now,
        )

        tk = _build_toolkit(run, exe)
        tools = tk.build_tools()
        list_my = tools[0]
        result = await list_my.function()

        assert len(result) == 2
        assert result[0].content_hash == "new"
        assert result[1].content_hash == "old"

    @pytest.mark.asyncio
    async def test_empty_when_no_resources(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        node = _seed_node(session, run)
        exe = _seed_execution(session, run, node_id=node.id)

        tk = _build_toolkit(run, exe)
        tools = tk.build_tools()
        result = await tools[0].function()
        assert result == []


# ---------------------------------------------------------------------------
# list_child_resources
# ---------------------------------------------------------------------------


class TestListChildResources:
    @pytest.mark.asyncio
    async def test_returns_only_direct_children_resources(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)

        parent_node = _seed_node(session, run, task_key="parent")
        child_node = _seed_node(session, run, task_key="child")
        grandchild_node = _seed_node(session, run, task_key="grandchild")

        _seed_edge(session, run, parent_node, child_node)
        _seed_edge(session, run, child_node, grandchild_node)

        parent_exe = _seed_execution(session, run, node_id=parent_node.id)
        child_exe = _seed_execution(session, run, node_id=child_node.id)
        grandchild_exe = _seed_execution(
            session,
            run,
            node_id=grandchild_node.id,
        )

        _seed_resource(
            session,
            run,
            child_exe,
            name="child.md",
            file_path="/workspace/child.md",
            content_hash="child_hash",
        )
        _seed_resource(
            session,
            run,
            grandchild_exe,
            name="gc.md",
            file_path="/workspace/gc.md",
            content_hash="gc_hash",
        )

        tk = _build_toolkit(run, parent_exe)
        tools = tk.build_tools()
        list_child = tools[1]
        result = await list_child.function()

        hashes = {r.content_hash for r in result}
        assert "child_hash" in hashes
        assert "gc_hash" not in hashes

    @pytest.mark.asyncio
    async def test_empty_when_no_children(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        node = _seed_node(session, run)
        exe = _seed_execution(session, run, node_id=node.id)

        tk = _build_toolkit(run, exe)
        tools = tk.build_tools()
        result = await tools[1].function()
        assert result == []


# ---------------------------------------------------------------------------
# list_descendant_resources
# ---------------------------------------------------------------------------


class TestListDescendantResources:
    @pytest.mark.asyncio
    async def test_respects_depth_bound(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """3-level tree: depth=1 gets child only, depth=2 adds grandchild,
        depth=3 adds great-grandchild."""
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)

        root_node = _seed_node(session, run, task_key="root")
        l1_node = _seed_node(session, run, task_key="l1")
        l2_node = _seed_node(session, run, task_key="l2")
        l3_node = _seed_node(session, run, task_key="l3")

        _seed_edge(session, run, root_node, l1_node)
        _seed_edge(session, run, l1_node, l2_node)
        _seed_edge(session, run, l2_node, l3_node)

        root_exe = _seed_execution(session, run, node_id=root_node.id)
        l1_exe = _seed_execution(session, run, node_id=l1_node.id)
        l2_exe = _seed_execution(session, run, node_id=l2_node.id)
        l3_exe = _seed_execution(session, run, node_id=l3_node.id)

        _seed_resource(
            session,
            run,
            l1_exe,
            name="l1.md",
            file_path="/workspace/l1.md",
            content_hash="l1",
        )
        _seed_resource(
            session,
            run,
            l2_exe,
            name="l2.md",
            file_path="/workspace/l2.md",
            content_hash="l2",
        )
        _seed_resource(
            session,
            run,
            l3_exe,
            name="l3.md",
            file_path="/workspace/l3.md",
            content_hash="l3",
        )

        tk = _build_toolkit(run, root_exe)
        tools = tk.build_tools()
        list_desc = tools[2]

        r1 = await list_desc.function(max_depth=1)
        assert {r.content_hash for r in r1} == {"l1"}

        r2 = await list_desc.function(max_depth=2)
        assert {r.content_hash for r in r2} == {"l1", "l2"}

        r3 = await list_desc.function(max_depth=3)
        assert {r.content_hash for r in r3} == {"l1", "l2", "l3"}

    @pytest.mark.asyncio
    async def test_handles_cycles(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Two nodes that point at each other should not loop forever."""
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)

        node_a = _seed_node(session, run, task_key="a")
        node_b = _seed_node(session, run, task_key="b")

        # Bidirectional edges -> cycle
        _seed_edge(session, run, node_a, node_b)
        _seed_edge(session, run, node_b, node_a)

        exe_a = _seed_execution(session, run, node_id=node_a.id)
        exe_b = _seed_execution(session, run, node_id=node_b.id)

        _seed_resource(
            session,
            run,
            exe_b,
            name="b.md",
            file_path="/workspace/b.md",
            content_hash="b_hash",
        )

        tk = _build_toolkit(run, exe_a)
        tools = tk.build_tools()
        list_desc = tools[2]

        result = await list_desc.function(max_depth=10)
        # Should terminate and find exactly 1 resource (from exe_b)
        assert len(result) == 1
        assert result[0].content_hash == "b_hash"

    @pytest.mark.asyncio
    async def test_empty_when_no_descendants(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        node = _seed_node(session, run)
        exe = _seed_execution(session, run, node_id=node.id)

        tk = _build_toolkit(run, exe)
        tools = tk.build_tools()
        result = await tools[2].function()
        assert result == []


# ---------------------------------------------------------------------------
# list_run_resources
# ---------------------------------------------------------------------------


class TestListRunResources:
    @pytest.mark.asyncio
    async def test_scopes_by_run_id(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run_a = _seed_run(session)
        run_b = _seed_run(session)

        node_a = _seed_node(session, run_a, task_key="a")
        node_b = _seed_node(session, run_b, task_key="b")

        exe_a = _seed_execution(session, run_a, node_id=node_a.id)
        exe_b = _seed_execution(session, run_b, node_id=node_b.id)

        _seed_resource(
            session,
            run_a,
            exe_a,
            name="a.md",
            file_path="/workspace/a.md",
            content_hash="a_hash",
        )
        _seed_resource(
            session,
            run_b,
            exe_b,
            name="b.md",
            file_path="/workspace/b.md",
            content_hash="b_hash",
        )

        tk = _build_toolkit(run_a, exe_a)
        tools = tk.build_tools()
        list_run = tools[3]
        result = await list_run.function()

        hashes = {r.content_hash for r in result}
        assert "a_hash" in hashes
        assert "b_hash" not in hashes


# ---------------------------------------------------------------------------
# get_resource_by_logical_path
# ---------------------------------------------------------------------------


class TestGetResourceByLogicalPath:
    @pytest.mark.asyncio
    async def test_returns_latest(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        node = _seed_node(session, run)
        exe = _seed_execution(session, run, node_id=node.id)

        now = _utcnow()
        _seed_resource(
            session,
            run,
            exe,
            name="draft.md",
            file_path="/workspace/draft.md",
            content_hash="v1",
            created_at=now - timedelta(seconds=10),
        )
        _seed_resource(
            session,
            run,
            exe,
            name="draft.md",
            file_path="/workspace/draft.md",
            content_hash="v2",
            created_at=now,
        )

        tk = _build_toolkit(run, exe)
        tools = tk.build_tools()
        get_by_path = tools[4]
        result = await get_by_path.function(logical_path="/workspace/draft.md")

        assert result is not None
        assert result.content_hash == "v2"

    @pytest.mark.asyncio
    async def test_run_scoped(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Resource from another run is NOT visible."""
        _patch_get_session(monkeypatch, session)
        run_a = _seed_run(session)
        run_b = _seed_run(session)

        node_a = _seed_node(session, run_a)
        node_b = _seed_node(session, run_b)

        exe_a = _seed_execution(session, run_a, node_id=node_a.id)
        exe_b = _seed_execution(session, run_b, node_id=node_b.id)

        _seed_resource(
            session,
            run_b,
            exe_b,
            name="secret.md",
            file_path="/workspace/secret.md",
            content_hash="other_run",
        )

        tk = _build_toolkit(run_a, exe_a)
        tools = tk.build_tools()
        get_by_path = tools[4]
        result = await get_by_path.function(
            logical_path="/workspace/secret.md",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        node = _seed_node(session, run)
        exe = _seed_execution(session, run, node_id=node.id)

        tk = _build_toolkit(run, exe)
        tools = tk.build_tools()
        result = await tools[4].function(logical_path="/nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# get_resource_by_content_hash
# ---------------------------------------------------------------------------


class TestGetResourceByContentHash:
    @pytest.mark.asyncio
    async def test_returns_latest(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        node = _seed_node(session, run)
        exe = _seed_execution(session, run, node_id=node.id)

        now = _utcnow()
        _seed_resource(
            session,
            run,
            exe,
            name="a.md",
            file_path="/workspace/a.md",
            content_hash="shared_hash",
            created_at=now - timedelta(seconds=10),
        )
        _seed_resource(
            session,
            run,
            exe,
            name="b.md",
            file_path="/workspace/b.md",
            content_hash="shared_hash",
            created_at=now,
        )

        tk = _build_toolkit(run, exe)
        tools = tk.build_tools()
        get_by_hash = tools[5]
        result = await get_by_hash.function(content_hash="shared_hash")

        assert result is not None
        # Most recent is b.md
        assert result.logical_path == "/workspace/b.md"

    @pytest.mark.asyncio
    async def test_run_scoped(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run_a = _seed_run(session)
        run_b = _seed_run(session)

        node_b = _seed_node(session, run_b)
        exe_b = _seed_execution(session, run_b, node_id=node_b.id)

        _seed_resource(
            session,
            run_b,
            exe_b,
            name="other.md",
            file_path="/workspace/other.md",
            content_hash="secret_hash",
        )

        node_a = _seed_node(session, run_a)
        exe_a = _seed_execution(session, run_a, node_id=node_a.id)

        tk = _build_toolkit(run_a, exe_a)
        tools = tk.build_tools()
        result = await tools[5].function(content_hash="secret_hash")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        node = _seed_node(session, run)
        exe = _seed_execution(session, run, node_id=node.id)

        tk = _build_toolkit(run, exe)
        tools = tk.build_tools()
        result = await tools[5].function(content_hash="nonexistent")
        assert result is None
