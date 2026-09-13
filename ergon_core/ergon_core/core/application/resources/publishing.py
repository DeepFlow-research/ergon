"""Application service for publishing run resources."""

import hashlib
from hashlib import sha256
from pathlib import Path
from pydantic import BaseModel, Field
import mimetypes
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TypeAlias
from uuid import UUID

from sqlmodel import Session

from ergon_core.core.application.ports import ResourceBlobWriter, SandboxFileReader
from ergon_core.core.application.resources.models import SampleResourceView
from ergon_core.core.application.resources.repository import SampleResourceRepository
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import SampleResourceKind

SessionFactory: TypeAlias = Callable[[], AbstractContextManager[Session]]


class SampleResourcePublishService:
    """Owns resource append/dedup semantics for sandbox outputs."""

    def __init__(
        self,
        *,
        repository: SampleResourceRepository | None = None,
        session_factory: SessionFactory = get_session,
    ) -> None:
        self._resource_repo = repository or SampleResourceRepository()
        self._session_factory = session_factory

    async def publish_sandbox_files(
        self,
        *,
        reader: SandboxFileReader,
        blob_store: ResourceBlobWriter,
        sample_id: UUID,
        task_attempt_id: UUID,
        publish_dirs: tuple[tuple[str, SampleResourceKind], ...],
    ) -> list[SampleResourceView]:
        """Publish changed files from configured sandbox dirs as run resources."""
        created: list[SampleResourceView] = []
        for sandbox_dir, resource_kind in publish_dirs:
            entries = await reader.list_sandbox_dir(sandbox_dir)
            for entry in entries:
                entry_name = reader.entry_name(entry)
                sandbox_full_path = reader.entry_path(sandbox_dir, entry)
                content_bytes = self._coerce_bytes(
                    await reader.read_sandbox_file(sandbox_full_path)
                )
                content_hash = self._content_hash(content_bytes)
                durable_path = blob_store.blob_path(content_hash)

                with self._session_factory() as session:
                    prior = self._resource_repo.latest_by_path(
                        session,
                        task_attempt_id=task_attempt_id,
                        file_path=str(durable_path),
                    )
                if prior is not None:
                    continue

                written_path = blob_store.write_blob(content_bytes, content_hash)

                with self._session_factory() as session:
                    row = self._resource_repo.append(
                        session,
                        sample_id=sample_id,
                        task_attempt_id=task_attempt_id,
                        kind=resource_kind.value,
                        name=entry_name,
                        mime_type=self._mime_type(entry_name),
                        file_path=str(written_path),
                        size_bytes=len(content_bytes),
                        error=None,
                        content_hash=content_hash,
                        metadata={"sandbox_origin": sandbox_full_path},
                    )
                    session.commit()
                    session.refresh(row)
                created.append(SampleResourceView.from_row(row))

        return created

    def publish_value(
        self,
        *,
        blob_store: ResourceBlobWriter,
        sample_id: UUID,
        task_attempt_id: UUID,
        kind: SampleResourceKind,
        name: str,
        content: str,
        mime_type: str = "text/plain",
    ) -> SampleResourceView | None:
        """Publish an explicit value as a run resource, deduping by content hash."""
        content_bytes = content.encode("utf-8")
        content_hash = self._content_hash(content_bytes)

        with self._session_factory() as session:
            prior = self._resource_repo.find_by_hash(
                session,
                task_attempt_id=task_attempt_id,
                content_hash=content_hash,
            )
        if prior is not None:
            return None

        durable_path = blob_store.write_blob(content_bytes, content_hash)

        with self._session_factory() as session:
            row = self._resource_repo.append(
                session,
                sample_id=sample_id,
                task_attempt_id=task_attempt_id,
                kind=kind.value,
                name=name,
                mime_type=mime_type,
                file_path=str(durable_path),
                size_bytes=len(content_bytes),
                error=None,
                content_hash=content_hash,
            )
            session.commit()
            session.refresh(row)
        return SampleResourceView.from_row(row)

    @staticmethod
    def _coerce_bytes(content: bytes | str) -> bytes:
        if isinstance(content, str):
            return content.encode("utf-8")
        return content

    @staticmethod
    def _content_hash(content_bytes: bytes) -> str:
        return hashlib.sha256(content_bytes).hexdigest()

    @staticmethod
    def _mime_type(name: str) -> str:
        guessed, _ = mimetypes.guess_type(name)
        return guessed or "application/octet-stream"


class CheckpointReference(BaseModel):
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class WorkerCheckpointStore:
    """Inngest owns the checkpoint; sample resources retain its result bytes.

    The reference is returned only after the blob and resource row commit.
    Missing/corrupt retained bytes fail replay rather than rerun the operation.
    """

    def __init__(
        self,
        blob_store: ResourceBlobWriter,
        sample_id: UUID,
        task_attempt_id: UUID,
        publisher: SampleResourcePublishService | None = None,
    ) -> None:
        self._blob_store = blob_store
        self._sample_id = sample_id
        self._task_attempt_id = task_attempt_id
        self._publisher = publisher or SampleResourcePublishService()

    def save(self, name: str, result: BaseModel) -> CheckpointReference:
        content = result.model_dump_json()
        data = content.encode("utf-8")
        self._publisher.publish_value(
            blob_store=self._blob_store,
            sample_id=self._sample_id,
            task_attempt_id=self._task_attempt_id,
            kind=SampleResourceKind.ARTIFACT,
            name=f".checkpoints/{name}.json",
            content=content,
            mime_type="application/json",
        )
        return CheckpointReference(content_hash=sha256(data).hexdigest(), size_bytes=len(data))

    def load(self, reference: CheckpointReference) -> bytes:
        data = Path(self._blob_store.blob_path(reference.content_hash)).read_bytes()
        if len(data) != reference.size_bytes or sha256(data).hexdigest() != reference.content_hash:
            raise ValueError(f"Checkpoint artifact integrity failure: {reference.content_hash}")
        return data
