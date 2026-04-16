"""SandboxResourcePublisher: blob-store writes, dedup, idempotence.

Uses a fake ``AsyncSandbox`` stub -- no real E2B container.  Database
interactions go through the shared SQLite session fixture with per-test
rollback.
"""

import hashlib
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResourceKind,
    RunTaskExecution,
)
from ergon_core.core.providers.sandbox.resource_publisher import (
    SandboxResourcePublisher,
)
from sqlmodel import Session

# ---------------------------------------------------------------------------
# Fake sandbox stubs
# ---------------------------------------------------------------------------


class _FakeEntry:
    """Mimics e2b ``EntryInfo`` returned by ``sandbox.files.list``."""

    def __init__(self, *, name: str) -> None:
        self.name = name


class _FakeSandboxFiles:
    """Stub for ``AsyncSandbox.files`` with in-memory filesystem."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    def put(self, path: str, content: bytes) -> None:
        """Test helper -- seed a file into the fake FS."""
        self._files[path] = content

    async def list(self, path: str) -> list[_FakeEntry]:
        prefix = path if path.endswith("/") else path + "/"
        entries: list[_FakeEntry] = []
        seen: set[str] = set()
        for key in self._files:
            if key.startswith(prefix):
                # Only direct children (no nested dirs).
                remainder = key[len(prefix) :]
                if "/" not in remainder and remainder not in seen:
                    entries.append(_FakeEntry(name=remainder))
                    seen.add(remainder)
        if not entries and prefix not in {
            k[: len(prefix)] for k in self._files if k.startswith(prefix)
        }:
            raise FileNotFoundError(path)
        return entries

    async def read(self, path: str, *, request_timeout: int = 30) -> bytes:
        if path not in self._files:
            raise FileNotFoundError(path)
        return self._files[path]


class _FakeSandbox:
    """Minimal ``AsyncSandbox`` stand-in."""

    def __init__(self) -> None:
        self.files = _FakeSandboxFiles()


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
# Tests: sync()
# ---------------------------------------------------------------------------


class TestSync:
    @pytest.mark.asyncio
    async def test_creates_one_row_per_file(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        sandbox = _FakeSandbox()
        sandbox.files.put("/workspace/final_output/report.md", b"# Hello World")
        sandbox.files.put("/workspace/final_output/notes.txt", b"Some notes")

        publisher = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe.id,
            blob_root=tmp_path,
        )

        created = await publisher.sync()
        assert len(created) == 2

        names = {v.name for v in created}
        assert names == {"report.md", "notes.txt"}

        # Verify blobs written to disk
        for view in created:
            blob = Path(view.file_path)
            assert blob.exists()
            content_hash = view.content_hash
            assert content_hash is not None
            expected_path = tmp_path / content_hash[:2] / content_hash
            assert blob == expected_path

    @pytest.mark.asyncio
    async def test_sync_twice_no_change_is_noop(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        sandbox = _FakeSandbox()
        sandbox.files.put("/workspace/final_output/report.md", b"# Hello")

        publisher = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe.id,
            blob_root=tmp_path,
        )

        first = await publisher.sync()
        assert len(first) == 1

        second = await publisher.sync()
        assert second == []

        # Only one blob on disk
        blobs = list(tmp_path.rglob("*"))
        blob_files = [b for b in blobs if b.is_file()]
        assert len(blob_files) == 1

    @pytest.mark.asyncio
    async def test_changed_content_appends_new_row(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        sandbox = _FakeSandbox()
        sandbox.files.put("/workspace/final_output/report.md", b"version 1")

        publisher = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe.id,
            blob_root=tmp_path,
        )

        first = await publisher.sync()
        assert len(first) == 1

        # Change file content
        sandbox.files.put("/workspace/final_output/report.md", b"version 2")

        second = await publisher.sync()
        assert len(second) == 1
        assert second[0].content_hash != first[0].content_hash

        # Both blobs exist on disk (append-only)
        old_blob = Path(first[0].file_path)
        new_blob = Path(second[0].file_path)
        assert old_blob.exists()
        assert new_blob.exists()
        assert old_blob != new_blob

        # Both rows survive in the DB
        all_rows = queries.resources.list_by_execution(exe.id)
        assert len(all_rows) == 2


# ---------------------------------------------------------------------------
# Tests: publish_value()
# ---------------------------------------------------------------------------


class TestPublishValue:
    def test_writes_blob_and_creates_row(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        sandbox = _FakeSandbox()
        publisher = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe.id,
            blob_root=tmp_path,
        )

        content = "The quick brown fox"
        view = publisher.publish_value(
            kind=RunResourceKind.OUTPUT,
            name="worker_output",
            content=content,
        )

        assert view is not None
        assert view.kind == RunResourceKind.OUTPUT
        assert view.name == "worker_output"
        assert view.mime_type == "text/plain"
        assert view.content_hash == _sha256(content.encode())

        blob = Path(view.file_path)
        assert blob.exists()
        assert blob.read_bytes() == content.encode()

    def test_dedup_by_hash(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        sandbox = _FakeSandbox()
        publisher = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe.id,
            blob_root=tmp_path,
        )

        first = publisher.publish_value(
            kind=RunResourceKind.OUTPUT,
            name="worker_output",
            content="same content",
        )
        assert first is not None

        second = publisher.publish_value(
            kind=RunResourceKind.OUTPUT,
            name="worker_output",
            content="same content",
        )
        assert second is None

        all_rows = queries.resources.list_by_execution(exe.id)
        assert len(all_rows) == 1


# ---------------------------------------------------------------------------
# Tests: missing PUBLISH_DIRS directory
# ---------------------------------------------------------------------------


class TestMissingDir:
    @pytest.mark.asyncio
    async def test_missing_publish_dir_returns_empty(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        # Sandbox has no files at all -- PUBLISH_DIRS directory is missing.
        sandbox = _FakeSandbox()

        publisher = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe.id,
            blob_root=tmp_path,
        )

        result = await publisher.sync()
        assert result == []


# ---------------------------------------------------------------------------
# Tests: atomic blob writes
# ---------------------------------------------------------------------------


class TestAtomicBlobWrite:
    def test_no_tmp_file_remains_after_write(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        sandbox = _FakeSandbox()
        publisher = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe.id,
            blob_root=tmp_path,
        )

        content = "atomic write test"
        publisher.publish_value(
            kind=RunResourceKind.NOTE,
            name="test",
            content=content,
        )

        # No .tmp files should remain anywhere under blob_root.
        tmp_files = list(tmp_path.rglob("*.tmp"))
        assert tmp_files == [], f"Stale .tmp files found: {tmp_files}"

    @pytest.mark.asyncio
    async def test_blob_write_idempotent(
        self,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        """Writing the same content twice doesn't corrupt the blob."""
        _patch_get_session(monkeypatch, session)
        run = _seed_run(session)
        exe = _seed_execution(session, run)

        sandbox = _FakeSandbox()
        publisher = SandboxResourcePublisher(
            sandbox=sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=exe.id,
            blob_root=tmp_path,
        )

        content_bytes = b"idempotent blob"
        content_hash = _sha256(content_bytes)

        path1 = publisher._write_blob(content_bytes, content_hash)
        path2 = publisher._write_blob(content_bytes, content_hash)

        assert path1 == path2
        assert path1.read_bytes() == content_bytes
