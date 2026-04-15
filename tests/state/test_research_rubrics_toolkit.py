"""ResearchRubricsToolkit + ResearchRubricsSandboxManager integration tests.

Uses a fake AsyncSandbox stub that records commands and file writes --
no real E2B container.  Database interactions go through the shared
SQLite session fixture with per-test rollback.
"""

import hashlib
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_builtins.benchmarks.researchrubrics.toolkit_types import (
    DocumentFailure,
    DocumentSuccess,
    QASuccess,
    ReportReadSuccess,
    ReportWriteFailure,
    ReportWriteSuccess,
    SearchSuccess,
)
from ergon_builtins.tools.research_rubrics_toolkit import (
    ResearchRubricsToolkit,
)
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.shared.enums import (
    RunStatus,
    TaskExecutionStatus,
)
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResourceKind,
    RunTaskExecution,
)
from ergon_core.core.providers.sandbox.resource_publisher import (
    SandboxResourcePublisher,
)


# ---------------------------------------------------------------------------
# Fake sandbox stubs (mirrors test_sandbox_resource_publisher.py)
# ---------------------------------------------------------------------------


class _FakeEntry:
    """Mimics e2b ``EntryInfo`` returned by ``sandbox.files.list``."""

    def __init__(self, *, name: str) -> None:
        self.name = name


class _FakeCommandResult:
    """Mimics e2b command execution result."""

    def __init__(
        self,
        *,
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class _FakeSandboxCommands:
    """Stub for ``AsyncSandbox.commands``."""

    def __init__(self) -> None:
        self.history: list[str] = []

    async def run(
        self,
        cmd: str,
        timeout: int = 60,
    ) -> _FakeCommandResult:
        self.history.append(cmd)
        return _FakeCommandResult()


class _FakeSandboxFiles:
    """Stub for ``AsyncSandbox.files`` with in-memory filesystem."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    def put(self, path: str, content: bytes) -> None:
        """Test helper -- seed a file into the fake FS."""
        self._files[path] = content

    async def write(self, path: str, content: bytes) -> None:
        """Mimics ``sandbox.files.write``."""
        self._files[path] = content

    async def list(self, path: str) -> list[_FakeEntry]:
        prefix = path if path.endswith("/") else path + "/"
        entries: list[_FakeEntry] = []
        seen: set[str] = set()
        for key in self._files:
            if key.startswith(prefix):
                remainder = key[len(prefix) :]
                if "/" not in remainder and remainder not in seen:
                    entries.append(_FakeEntry(name=remainder))
                    seen.add(remainder)
        if not entries and prefix not in {
            k[: len(prefix)] for k in self._files if k.startswith(prefix)
        }:
            raise FileNotFoundError(path)
        return entries

    async def read(
        self,
        path: str,
        *,
        request_timeout: int = 30,
    ) -> bytes:
        if path not in self._files:
            raise FileNotFoundError(path)
        return self._files[path]


class _FakeSandbox:
    """Minimal ``AsyncSandbox`` stand-in."""

    def __init__(self) -> None:
        self.files = _FakeSandboxFiles()
        self.commands = _FakeSandboxCommands()
        self.sandbox_id = "fake-sandbox-id"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_get_session(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
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


def _seed_execution(session: Session, run: RunRecord) -> RunTaskExecution:
    exe = RunTaskExecution(
        id=uuid4(),
        run_id=run.id,
        status=TaskExecutionStatus.RUNNING,
    )
    session.add(exe)
    session.flush()
    return exe


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Skill-call fake: records invocations and returns canned DTOs
# ---------------------------------------------------------------------------


def _fake_exa_search(
    sandbox: _FakeSandbox,
    **kwargs: object,
) -> SearchSuccess:
    return SearchSuccess(
        query=str(kwargs.get("query", "")),
        results=[],
        latency_ms=10.0,
    )


def _fake_exa_qa(
    sandbox: _FakeSandbox,
    **kwargs: object,
) -> QASuccess:
    return QASuccess(
        question=str(kwargs.get("question", "")),
        answer="42",
        sources=[],
        latency_ms=15.0,
    )


def _fake_exa_get_content(
    sandbox: _FakeSandbox,
    **kwargs: object,
) -> DocumentSuccess | DocumentFailure:
    url = str(kwargs.get("url", ""))
    if url == "https://empty.example.com":
        return DocumentFailure(
            url=url,
            reason="empty",
            detail="No text extracted",
            latency_ms=5.0,
        )
    return DocumentSuccess(
        url=url,
        title="Example",
        text="Hello world",
        word_count=2,
        latency_ms=12.0,
    )


def _fake_write_report(
    sandbox: _FakeSandbox,
    **kwargs: object,
) -> ReportWriteSuccess | ReportWriteFailure:
    rp = str(kwargs.get("relative_path", ""))
    content = str(kwargs.get("content", ""))
    if rp.startswith("..") or rp.startswith("/"):
        return ReportWriteFailure(
            path=rp,
            reason="path_disallowed",
            detail="Path escapes /workspace/",
            latency_ms=1.0,
        )
    sandbox.files.put(f"/workspace/final_output/{rp}", content.encode())
    return ReportWriteSuccess(
        path=f"final_output/{rp}",
        bytes_written=len(content.encode()),
        latency_ms=8.0,
    )


def _fake_edit_report(
    sandbox: _FakeSandbox,
    **kwargs: object,
) -> ReportWriteSuccess | ReportWriteFailure:
    rp = str(kwargs.get("relative_path", ""))
    patch = str(kwargs.get("patch", ""))
    if rp.startswith("..") or rp.startswith("/"):
        return ReportWriteFailure(
            path=rp,
            reason="path_disallowed",
            detail="Path escapes /workspace/",
            latency_ms=1.0,
        )
    sandbox.files.put(f"/workspace/final_output/{rp}", patch.encode())
    return ReportWriteSuccess(
        path=f"final_output/{rp}",
        bytes_written=len(patch.encode()),
        latency_ms=6.0,
    )


def _fake_read_report(
    sandbox: _FakeSandbox,
    **kwargs: object,
) -> ReportReadSuccess:
    from ergon_builtins.benchmarks.researchrubrics.toolkit_types import (
        ReportReadFailure,
    )

    rp = str(kwargs.get("relative_path", ""))
    stored = sandbox.files._files.get(f"/workspace/final_output/{rp}")
    if stored is None:
        return ReportReadFailure(  # type: ignore[return-value]
            path=rp,
            reason="not_found",
            detail="File not found",
            latency_ms=2.0,
        )
    return ReportReadSuccess(
        path=rp,
        content=stored.decode(),
        size_bytes=len(stored),
        latency_ms=3.0,
    )


_SKILL_DISPATCH: dict[str, object] = {
    "exa_search": _fake_exa_search,
    "exa_qa": _fake_exa_qa,
    "exa_get_content": _fake_exa_get_content,
    "write_report_draft": _fake_write_report,
    "edit_report_draft": _fake_edit_report,
    "read_report_draft": _fake_read_report,
}


class _SkillRecorder:
    """Fake ``run_skill`` that records calls and returns canned responses.

    Also writes files into the fake sandbox FS for write/edit skills so
    that ``publisher.sync()`` can find them.
    """

    def __init__(self, sandbox: _FakeSandbox) -> None:
        self.calls: list[tuple[str, object]] = []
        self._sandbox = sandbox

    async def __call__(
        self,
        skill_name: str,
        response_model: type,  # type: ignore[type-arg]
        **kwargs: object,
    ) -> object:
        self.calls.append((skill_name, kwargs))
        handler = _SKILL_DISPATCH.get(skill_name)
        if handler is None:
            raise ValueError(f"Unknown skill: {skill_name}")
        return handler(self._sandbox, **kwargs)  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sandbox() -> _FakeSandbox:
    return _FakeSandbox()


@pytest.fixture
def db_context(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[RunRecord, RunTaskExecution]:
    _patch_get_session(monkeypatch, session)
    run = _seed_run(session)
    exe = _seed_execution(session, run)
    return run, exe


@pytest.fixture
def publisher(
    sandbox: _FakeSandbox,
    db_context: tuple[RunRecord, RunTaskExecution],
    tmp_path: Path,
) -> SandboxResourcePublisher:
    run, exe = db_context
    return SandboxResourcePublisher(
        sandbox=sandbox,  # type: ignore[arg-type]
        run_id=run.id,
        task_execution_id=exe.id,
        blob_root=tmp_path,
    )


@pytest.fixture
def skill_recorder(sandbox: _FakeSandbox) -> _SkillRecorder:
    return _SkillRecorder(sandbox)


@pytest.fixture
def toolkit(
    skill_recorder: _SkillRecorder,
    publisher: SandboxResourcePublisher,
) -> ResearchRubricsToolkit:
    return ResearchRubricsToolkit(
        run_skill=skill_recorder,
        publisher_sync=publisher.sync,
    )


# ---------------------------------------------------------------------------
# Tests: build_tools()
# ---------------------------------------------------------------------------


class TestBuildTools:
    def test_returns_six_tools(self, toolkit: ResearchRubricsToolkit):
        tools = toolkit.build_tools()
        assert len(tools) == 6

    def test_tool_names(self, toolkit: ResearchRubricsToolkit):
        tools = toolkit.build_tools()
        names = {t.name for t in tools}
        assert names == {
            "exa_search",
            "exa_qa",
            "exa_get_content",
            "write_report_draft",
            "edit_report_draft",
            "read_report_draft",
        }


# ---------------------------------------------------------------------------
# Tests: exa skill handlers
# ---------------------------------------------------------------------------


class TestExaSearch:
    @pytest.mark.asyncio
    async def test_happy_path(
        self,
        skill_recorder: _SkillRecorder,
        toolkit: ResearchRubricsToolkit,
    ):
        tools = toolkit.build_tools()
        exa_search = next(t for t in tools if t.name == "exa_search")
        result = await exa_search.function(query="quantum computing")
        assert result.kind == "success"
        assert result.query == "quantum computing"
        assert result.latency_ms > 0
        assert skill_recorder.calls[-1][0] == "exa_search"


class TestExaQA:
    @pytest.mark.asyncio
    async def test_happy_path(
        self,
        skill_recorder: _SkillRecorder,
        toolkit: ResearchRubricsToolkit,
    ):
        tools = toolkit.build_tools()
        exa_qa = next(t for t in tools if t.name == "exa_qa")
        result = await exa_qa.function(question="What is 6x7?")
        assert result.kind == "success"
        assert result.answer == "42"
        assert result.latency_ms > 0


class TestExaGetContent:
    @pytest.mark.asyncio
    async def test_happy_path(
        self,
        skill_recorder: _SkillRecorder,
        toolkit: ResearchRubricsToolkit,
    ):
        tools = toolkit.build_tools()
        tool = next(t for t in tools if t.name == "exa_get_content")
        result = await tool.function(url="https://example.com")
        assert result.kind == "success"
        assert result.word_count == 2

    @pytest.mark.asyncio
    async def test_empty_returns_failure(
        self,
        skill_recorder: _SkillRecorder,
        toolkit: ResearchRubricsToolkit,
    ):
        tools = toolkit.build_tools()
        tool = next(t for t in tools if t.name == "exa_get_content")
        result = await tool.function(url="https://empty.example.com")
        assert result.kind == "failure"
        assert result.reason == "empty"


# ---------------------------------------------------------------------------
# Tests: report drafting with RunResource persistence
# ---------------------------------------------------------------------------


class TestWriteReportDraft:
    @pytest.mark.asyncio
    async def test_happy_path_creates_run_resource(
        self,
        toolkit: ResearchRubricsToolkit,
        db_context: tuple[RunRecord, RunTaskExecution],
    ):
        run, exe = db_context
        tools = toolkit.build_tools()
        tool = next(t for t in tools if t.name == "write_report_draft")
        result = await tool.function(
            relative_path="report.md",
            content="# My Report\n\nFindings here.",
        )
        assert result.kind == "success"
        assert result.bytes_written > 0

        # Artifact should appear as a RunResource row
        rows = queries.resources.list_by_execution(exe.id)
        assert len(rows) >= 1
        report_rows = [r for r in rows if r.kind == RunResourceKind.REPORT.value]
        assert len(report_rows) == 1
        assert report_rows[0].name == "report.md"

    @pytest.mark.asyncio
    async def test_path_escape_rejected(
        self,
        toolkit: ResearchRubricsToolkit,
        db_context: tuple[RunRecord, RunTaskExecution],
    ):
        _, exe = db_context
        tools = toolkit.build_tools()
        tool = next(t for t in tools if t.name == "write_report_draft")
        result = await tool.function(
            relative_path="../escape.md",
            content="bad",
        )
        assert result.kind == "failure"
        assert result.reason == "path_disallowed"

        # No RunResource should have been created
        rows = queries.resources.list_by_execution(exe.id)
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_scratch_artifact_not_output_kind(
        self,
        sandbox: _FakeSandbox,
        db_context: tuple[RunRecord, RunTaskExecution],
        tmp_path: Path,
    ):
        """Scratch artifacts written to scratchpad don't become REPORT rows.

        The publisher only syncs PUBLISH_DIRS (/workspace/final_output/).
        Files placed under /workspace/scratchpad/ are invisible to sync().
        """
        run, exe = db_context
        publisher = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe.id,
            blob_root=tmp_path,
        )
        # Manually place a file under scratchpad
        sandbox.files.put("/workspace/scratchpad/notes.txt", b"scratch notes")

        created = await publisher.sync()
        assert created == []

        rows = queries.resources.list_by_execution(exe.id)
        assert len(rows) == 0


class TestEditReportDraft:
    @pytest.mark.asyncio
    async def test_edit_updates_resource(
        self,
        toolkit: ResearchRubricsToolkit,
        db_context: tuple[RunRecord, RunTaskExecution],
    ):
        run, exe = db_context
        tools = toolkit.build_tools()
        write_tool = next(t for t in tools if t.name == "write_report_draft")
        edit_tool = next(t for t in tools if t.name == "edit_report_draft")

        # Write initial
        await write_tool.function(
            relative_path="report.md",
            content="v1",
        )
        rows_v1 = queries.resources.list_by_execution(exe.id)
        assert len(rows_v1) == 1

        # Edit with different content
        result = await edit_tool.function(
            relative_path="report.md",
            patch="v2 -- updated content",
        )
        assert result.kind == "success"

        rows_v2 = queries.resources.list_by_execution(exe.id)
        # Append-only: two rows now
        assert len(rows_v2) == 2

    @pytest.mark.asyncio
    async def test_edit_identical_content_deduped(
        self,
        toolkit: ResearchRubricsToolkit,
        db_context: tuple[RunRecord, RunTaskExecution],
    ):
        """Editing with identical content does not create a new row."""
        _, exe = db_context
        tools = toolkit.build_tools()
        write_tool = next(t for t in tools if t.name == "write_report_draft")
        edit_tool = next(t for t in tools if t.name == "edit_report_draft")

        await write_tool.function(
            relative_path="report.md",
            content="same content",
        )
        rows_after_write = queries.resources.list_by_execution(exe.id)
        assert len(rows_after_write) == 1

        # Edit with *identical* content
        await edit_tool.function(
            relative_path="report.md",
            patch="same content",
        )
        rows_after_edit = queries.resources.list_by_execution(exe.id)
        # Content-hash dedup means no new row
        assert len(rows_after_edit) == 1


class TestReadReportDraft:
    @pytest.mark.asyncio
    async def test_read_after_write(
        self,
        toolkit: ResearchRubricsToolkit,
    ):
        """Read sees what was written by a prior skill call (composability)."""
        tools = toolkit.build_tools()
        write_tool = next(t for t in tools if t.name == "write_report_draft")
        read_tool = next(t for t in tools if t.name == "read_report_draft")

        await write_tool.function(
            relative_path="report.md",
            content="# Findings\n\nImportant stuff.",
        )
        result = await read_tool.function(relative_path="report.md")
        assert result.kind == "success"
        assert "Findings" in result.content

    @pytest.mark.asyncio
    async def test_read_nonexistent(
        self,
        toolkit: ResearchRubricsToolkit,
    ):
        tools = toolkit.build_tools()
        read_tool = next(t for t in tools if t.name == "read_report_draft")
        result = await read_tool.function(relative_path="nonexistent.md")
        assert result.kind == "failure"
        assert result.reason == "not_found"


# ---------------------------------------------------------------------------
# Tests: run-scoping
# ---------------------------------------------------------------------------


class TestRunScoping:
    @pytest.mark.asyncio
    async def test_resources_scoped_to_execution(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
        sandbox: _FakeSandbox,
        tmp_path: Path,
    ):
        """Resources created under one execution are not visible to another."""
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe_a = _seed_execution(session, run)
        exe_b = _seed_execution(session, run)

        recorder = _SkillRecorder(sandbox)
        pub_a = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe_a.id,
            blob_root=tmp_path,
        )
        toolkit_a = ResearchRubricsToolkit(
            run_skill=recorder,
            publisher_sync=pub_a.sync,
        )

        tools = toolkit_a.build_tools()
        write_tool = next(t for t in tools if t.name == "write_report_draft")
        await write_tool.function(
            relative_path="report.md",
            content="exe_a content",
        )

        rows_a = queries.resources.list_by_execution(exe_a.id)
        rows_b = queries.resources.list_by_execution(exe_b.id)
        assert len(rows_a) == 1
        assert len(rows_b) == 0


# ---------------------------------------------------------------------------
# Tests: ResearchRubricsSandboxManager
# ---------------------------------------------------------------------------


class TestResearchRubricsSandboxManager:
    @pytest.mark.asyncio
    async def test_install_dependencies_runs_pip_and_mkdir(self):
        from ergon_core.core.providers.sandbox.research_rubrics_manager import (
            ResearchRubricsSandboxManager,
        )

        sandbox = _FakeSandbox()
        mgr = ResearchRubricsSandboxManager()
        await mgr._install_dependencies(sandbox, uuid4())  # type: ignore[arg-type]

        cmds = sandbox.commands.history
        # Should have pip install + 3 mkdir calls
        assert any("pip install" in c and "exa-py" in c for c in cmds)
        assert any("mkdir -p /workspace/scratchpad" in c for c in cmds)
        assert any("mkdir -p /workspace/final_output" in c for c in cmds)
        assert any("mkdir -p /workspace/researchers" in c for c in cmds)

    def test_publisher_for_raises_on_missing_sandbox(self):
        from ergon_core.core.providers.sandbox.research_rubrics_manager import (
            ResearchRubricsSandboxManager,
        )

        mgr = ResearchRubricsSandboxManager()
        with pytest.raises(KeyError):
            mgr.publisher_for(
                task_id=uuid4(),
                run_id=uuid4(),
                task_execution_id=uuid4(),
            )

    def test_publisher_for_returns_publisher_when_sandbox_exists(self):
        from ergon_core.core.providers.sandbox.research_rubrics_manager import (
            ResearchRubricsSandboxManager,
        )

        mgr = ResearchRubricsSandboxManager()
        task_id = uuid4()
        sandbox = _FakeSandbox()
        # Manually register a sandbox (simulates what create() does)
        mgr._sandboxes[task_id] = sandbox  # type: ignore[assignment]
        try:
            pub = mgr.publisher_for(
                task_id=task_id,
                run_id=uuid4(),
                task_execution_id=uuid4(),
            )
            assert isinstance(pub, SandboxResourcePublisher)
        finally:
            # Clean up singleton state
            mgr._sandboxes.pop(task_id, None)

    def test_singleton_behavior(self):
        from ergon_core.core.providers.sandbox.research_rubrics_manager import (
            ResearchRubricsSandboxManager,
        )

        a = ResearchRubricsSandboxManager()
        b = ResearchRubricsSandboxManager()
        assert a is b
