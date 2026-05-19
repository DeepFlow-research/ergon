"""Application service for publishing run resources."""

import hashlib
import mimetypes
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TypeAlias
from uuid import UUID

from sqlmodel import Session

from ergon_core.core.application.ports.resources import ResourceBlobWriter, SandboxFileReader
from ergon_core.core.application.resources.models import RunResourceView
from ergon_core.core.application.resources.repository import RunResourceRepository
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunResourceKind

SessionFactory: TypeAlias = Callable[[], AbstractContextManager[Session]]


class RunResourcePublishService:
    """Owns resource append/dedup semantics for sandbox outputs."""

    def __init__(
        self,
        *,
        repository: RunResourceRepository | None = None,
        session_factory: SessionFactory = get_session,
    ) -> None:
        self._resource_repo = repository or RunResourceRepository()
        self._session_factory = session_factory

    async def publish_sandbox_files(
        self,
        *,
        reader: SandboxFileReader,
        blob_store: ResourceBlobWriter,
        run_id: UUID,
        task_execution_id: UUID,
        publish_dirs: tuple[tuple[str, RunResourceKind], ...],
    ) -> list[RunResourceView]:
        """Publish changed files from configured sandbox dirs as run resources."""
        created: list[RunResourceView] = []
        for sandbox_dir, resource_kind in publish_dirs:
            entries = await reader.list_sandbox_dir(sandbox_dir)
            for entry in entries:
                entry_name = reader.entry_name(entry)
                sandbox_full_path = reader.entry_path(sandbox_dir, entry)
                content_bytes = self._coerce_bytes(await reader.read_sandbox_file(sandbox_full_path))
                content_hash = self._content_hash(content_bytes)
                durable_path = blob_store.blob_path(content_hash)

                with self._session_factory() as session:
                    prior = self._resource_repo.latest_by_path(
                        session,
                        task_execution_id=task_execution_id,
                        file_path=str(durable_path),
                    )
                if prior is not None:
                    continue

                written_path = blob_store.write_blob(content_bytes, content_hash)

                with self._session_factory() as session:
                    row = self._resource_repo.append(
                        session,
                        run_id=run_id,
                        task_execution_id=task_execution_id,
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
                created.append(RunResourceView.from_row(row))

        return created

    def publish_value(
        self,
        *,
        blob_store: ResourceBlobWriter,
        run_id: UUID,
        task_execution_id: UUID,
        kind: RunResourceKind,
        name: str,
        content: str,
        mime_type: str = "text/plain",
    ) -> RunResourceView | None:
        """Publish an explicit value as a run resource, deduping by content hash."""
        content_bytes = content.encode("utf-8")
        content_hash = self._content_hash(content_bytes)

        with self._session_factory() as session:
            prior = self._resource_repo.find_by_hash(
                session,
                task_execution_id=task_execution_id,
                content_hash=content_hash,
            )
        if prior is not None:
            return None

        durable_path = blob_store.write_blob(content_bytes, content_hash)

        with self._session_factory() as session:
            row = self._resource_repo.append(
                session,
                run_id=run_id,
                task_execution_id=task_execution_id,
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
        return RunResourceView.from_row(row)

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
