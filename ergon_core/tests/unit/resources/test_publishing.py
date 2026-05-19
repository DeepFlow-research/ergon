from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.persistence.shared.enums import RunResourceKind


class _Entry:
    name = "report.md"


class _Reader:
    async def list_sandbox_dir(self, path: str) -> list[_Entry]:
        assert path == "/workspace/final_output/"
        return [_Entry()]

    async def read_sandbox_file(self, path: str) -> bytes:
        assert path == "/workspace/final_output/report.md"
        return b"# report"

    def entry_name(self, entry: _Entry) -> str:
        return entry.name

    def entry_path(self, sandbox_dir: str, entry: _Entry) -> str:
        return f"{sandbox_dir.rstrip('/')}/{entry.name}"


class _BlobStore:
    def __init__(self) -> None:
        self.writes: list[tuple[bytes, str]] = []

    def blob_path(self, content_hash: str) -> str:
        return f"/blob/{content_hash[:2]}/{content_hash}"

    def write_blob(self, content_bytes: bytes, content_hash: str) -> str:
        self.writes.append((content_bytes, content_hash))
        return self.blob_path(content_hash)


class _Repository:
    def __init__(self, *, prior_by_path=None, prior_by_hash=None) -> None:
        self.prior_by_path = prior_by_path
        self.prior_by_hash = prior_by_hash
        self.appended: list[dict] = []

    def latest_by_path(self, _session, *, task_execution_id, file_path):
        del task_execution_id, file_path
        return self.prior_by_path

    def find_by_hash(self, _session, *, task_execution_id, content_hash):
        del task_execution_id, content_hash
        return self.prior_by_hash

    def append(self, _session, **kwargs):
        self.appended.append(kwargs)
        return SimpleNamespace(
            id=uuid4(),
            created_at=datetime.now(UTC),
            metadata_json=kwargs.get("metadata") or {},
            **kwargs,
        )


class _Session:
    def __init__(self) -> None:
        self.commits = 0
        self.refreshed: list[object] = []

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, row: object) -> None:
        self.refreshed.append(row)


@contextmanager
def _session_factory(session: _Session):
    yield session


@pytest.mark.asyncio
async def test_publish_sandbox_files_writes_blob_and_appends_resource_row() -> None:
    from ergon_core.core.application.resources.publishing import RunResourcePublishService

    run_id = uuid4()
    execution_id = uuid4()
    session = _Session()
    repository = _Repository()
    blob_store = _BlobStore()
    service = RunResourcePublishService(
        repository=repository,
        session_factory=lambda: _session_factory(session),
    )

    created = await service.publish_sandbox_files(
        reader=_Reader(),
        blob_store=blob_store,
        run_id=run_id,
        task_execution_id=execution_id,
        publish_dirs=(("/workspace/final_output/", RunResourceKind.REPORT),),
    )

    assert len(created) == 1
    appended = repository.appended[0]
    assert appended["run_id"] == run_id
    assert appended["task_execution_id"] == execution_id
    assert appended["kind"] == RunResourceKind.REPORT.value
    assert appended["name"] == "report.md"
    assert appended["mime_type"] == "text/markdown"
    assert appended["size_bytes"] == len(b"# report")
    assert appended["metadata"] == {"sandbox_origin": "/workspace/final_output/report.md"}
    assert blob_store.writes == [(b"# report", appended["content_hash"])]
    assert created[0].file_path == blob_store.blob_path(appended["content_hash"])
    assert session.commits == 1


@pytest.mark.asyncio
async def test_publish_sandbox_files_skips_existing_blob_path_without_writing() -> None:
    from ergon_core.core.application.resources.publishing import RunResourcePublishService

    session = _Session()
    repository = _Repository(prior_by_path=object())
    blob_store = _BlobStore()
    service = RunResourcePublishService(
        repository=repository,
        session_factory=lambda: _session_factory(session),
    )

    created = await service.publish_sandbox_files(
        reader=_Reader(),
        blob_store=blob_store,
        run_id=uuid4(),
        task_execution_id=uuid4(),
        publish_dirs=(("/workspace/final_output/", RunResourceKind.REPORT),),
    )

    assert created == []
    assert blob_store.writes == []
    assert repository.appended == []
    assert session.commits == 0


def test_publish_value_dedups_by_hash_before_blob_write() -> None:
    from ergon_core.core.application.resources.publishing import RunResourcePublishService

    repository = _Repository(prior_by_hash=object())
    blob_store = _BlobStore()
    service = RunResourcePublishService(
        repository=repository,
        session_factory=lambda: _session_factory(_Session()),
    )

    created = service.publish_value(
        blob_store=blob_store,
        run_id=uuid4(),
        task_execution_id=uuid4(),
        kind=RunResourceKind.REPORT,
        name="summary.txt",
        content="already present",
    )

    assert created is None
    assert blob_store.writes == []
    assert repository.appended == []
