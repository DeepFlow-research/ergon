"""HTTP tests for the resource-content endpoint backing the file-viewer modal.

``GET /runs/{run_id}/resources/{resource_id}/content`` streams bytes out of the
content-addressed blob store.  These tests cover the path-traversal guard, the
cross-run isolation, the 413 size cap, and 404s for missing rows / missing
blobs.
"""

from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from ergon_core.core.api import runs as runs_module
from ergon_core.core.api.runs import router as runs_router
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunResourceKind,
    RunTaskExecution,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def client(session: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    @contextmanager
    def _test_session():
        yield session

    # Patch get_session as used inside the runs module (the endpoint does
    # ``with get_session() as session``).
    monkeypatch.setattr(runs_module, "get_session", _test_session)

    app = FastAPI()
    app.include_router(runs_router)
    return TestClient(app)


@pytest.fixture
def blob_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "blob"
    root.mkdir()
    monkeypatch.setenv("ERGON_BLOB_ROOT", str(root))
    return root


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


def _write_blob(root: Path, content: bytes, content_hash: str) -> Path:
    path = root / content_hash[:2] / content_hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _seed_resource(
    session: Session,
    *,
    run_id: UUID,
    execution_id: UUID,
    file_path: str,
    size_bytes: int,
    content_hash: str,
    name: str = "draft.md",
    mime_type: str = "text/markdown",
) -> RunResource:
    row = RunResource(
        run_id=run_id,
        task_execution_id=execution_id,
        kind=RunResourceKind.REPORT.value,
        name=name,
        mime_type=mime_type,
        file_path=file_path,
        size_bytes=size_bytes,
        content_hash=content_hash,
    )
    session.add(row)
    session.flush()
    return row


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_returns_blob_bytes_with_inline_disposition(
    client: TestClient,
    blob_root: Path,
    session: Session,
):
    content = b"# hello\n\njust some markdown\n"
    content_hash = "a" * 64
    blob_path = _write_blob(blob_root, content, content_hash)

    run = _seed_run(session)
    exe = _seed_execution(session, run)
    resource = _seed_resource(
        session,
        run_id=run.id,
        execution_id=exe.id,
        file_path=str(blob_path),
        size_bytes=len(content),
        content_hash=content_hash,
    )

    resp = client.get(f"/runs/{run.id}/resources/{resource.id}/content")

    assert resp.status_code == 200
    assert resp.content == content
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "inline" in resp.headers.get("content-disposition", "")
    assert "draft.md" in resp.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# 404 cases
# ---------------------------------------------------------------------------


def test_unknown_resource_id_returns_404(client: TestClient, blob_root: Path, session: Session):
    run = _seed_run(session)
    resp = client.get(f"/runs/{run.id}/resources/{uuid4()}/content")
    assert resp.status_code == 404


def test_cross_run_resource_returns_404(
    client: TestClient,
    blob_root: Path,
    session: Session,
):
    """Resource belongs to run A; asking for it under run B 404s."""
    content = b"secret"
    content_hash = "b" * 64
    blob_path = _write_blob(blob_root, content, content_hash)

    run_a = _seed_run(session)
    exe = _seed_execution(session, run_a)
    resource = _seed_resource(
        session,
        run_id=run_a.id,
        execution_id=exe.id,
        file_path=str(blob_path),
        size_bytes=len(content),
        content_hash=content_hash,
    )

    run_b = _seed_run(session)
    resp = client.get(f"/runs/{run_b.id}/resources/{resource.id}/content")
    assert resp.status_code == 404


def test_missing_blob_file_returns_404(
    client: TestClient,
    blob_root: Path,
    session: Session,
):
    """Row points at a path that doesn't exist on disk."""
    run = _seed_run(session)
    exe = _seed_execution(session, run)
    resource = _seed_resource(
        session,
        run_id=run.id,
        execution_id=exe.id,
        file_path=str(blob_root / "aa" / ("c" * 64)),
        size_bytes=10,
        content_hash="c" * 64,
    )
    resp = client.get(f"/runs/{run.id}/resources/{resource.id}/content")
    assert resp.status_code == 404


def test_blob_outside_root_returns_404(
    client: TestClient,
    blob_root: Path,
    session: Session,
    tmp_path: Path,
):
    """A row whose file_path resolves outside ERGON_BLOB_ROOT is rejected."""
    rogue = tmp_path / "rogue.txt"
    rogue.write_bytes(b"pretend-traversal")

    run = _seed_run(session)
    exe = _seed_execution(session, run)
    resource = _seed_resource(
        session,
        run_id=run.id,
        execution_id=exe.id,
        file_path=str(rogue),
        size_bytes=rogue.stat().st_size,
        content_hash="d" * 64,
    )
    resp = client.get(f"/runs/{run.id}/resources/{resource.id}/content")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 413 size cap
# ---------------------------------------------------------------------------


def test_oversize_returns_413(
    client: TestClient,
    blob_root: Path,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """Shrink the cap so we don't need to materialize a 10 MiB file."""
    monkeypatch.setattr(runs_module, "_RESOURCE_CONTENT_MAX_BYTES", 8)

    content = b"way-too-much-for-eight-bytes"
    content_hash = "e" * 64
    blob_path = _write_blob(blob_root, content, content_hash)

    run = _seed_run(session)
    exe = _seed_execution(session, run)
    resource = _seed_resource(
        session,
        run_id=run.id,
        execution_id=exe.id,
        file_path=str(blob_path),
        size_bytes=len(content),
        content_hash=content_hash,
    )
    resp = client.get(f"/runs/{run.id}/resources/{resource.id}/content")
    assert resp.status_code == 413
