"""Append-only publisher for sandbox artifacts to the RunResource log.

Copies bytes out of an E2B sandbox into a content-addressed blob store on
the local filesystem, then appends one row per new hash to ``run_resources``.
All persistence goes through ``queries.resources`` (no session parameter).
"""

import hashlib
import logging
import mimetypes
import os
from pathlib import Path
from typing import ClassVar
from uuid import UUID

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]

from ergon_core.api.run_resource import RunResourceView
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.telemetry.models import RunResourceKind

logger = logging.getLogger(__name__)

_DEFAULT_BLOB_ROOT = Path(os.environ.get("ERGON_BLOB_ROOT", "/var/ergon/blob"))


class SandboxResourcePublisher:
    """Append-only publisher for RunResource rows.

    Every call that results in a new content hash writes the bytes to the
    content-addressed blob store at ``${ERGON_BLOB_ROOT}/<hash[:2]>/<hash>``
    and appends one row to ``run_resources``.  Never updates.  Content-hash
    dedup makes repeated calls safe.
    """

    # (sandbox_path, resource_kind) -- directories scanned by sync().
    PUBLISH_DIRS: ClassVar[list[tuple[str, RunResourceKind]]] = [
        ("/workspace/final_output/", RunResourceKind.REPORT),
    ]

    def __init__(
        self,
        *,
        sandbox: AsyncSandbox,
        run_id: UUID,
        task_execution_id: UUID,
        blob_root: Path = _DEFAULT_BLOB_ROOT,
    ) -> None:
        self._sandbox = sandbox
        self._run_id = run_id
        self._task_execution_id = task_execution_id
        self._blob_root = blob_root

    # ------------------------------------------------------------------
    # Filesystem sync -- called from write-type toolkit methods and from
    # persist_outputs_fn at task end.
    # ------------------------------------------------------------------

    async def sync(self) -> list[RunResourceView]:
        """Scan ``PUBLISH_DIRS``; append one row for each file whose
        ``content_hash`` differs from the current latest row at that sandbox
        path.  Returns Views for the rows that were created (empty if nothing
        changed).
        """
        created: list[RunResourceView] = []
        for sandbox_dir, resource_kind in self.PUBLISH_DIRS:
            entries = await self._list_sandbox_dir(sandbox_dir)
            for entry in entries:
                sandbox_full_path = f"{sandbox_dir}{entry.name}"
                content_bytes = await self._sandbox.files.read(
                    sandbox_full_path,
                    request_timeout=30,
                )
                if isinstance(content_bytes, str):
                    content_bytes = content_bytes.encode("utf-8")
                content_hash = hashlib.sha256(content_bytes).hexdigest()

                # Durable path is content-addressed: identical bytes -> identical
                # path.  Any existing row with this file_path in the current task
                # execution is proof the content is already logged.
                durable_path = self._blob_path(content_hash)
                prior = queries.resources.latest_by_path(
                    task_execution_id=self._task_execution_id,
                    file_path=str(durable_path),
                )
                if prior is not None:
                    continue  # unchanged

                self._write_blob(content_bytes, content_hash)

                # reason: inline mimetypes to keep module-level namespace clean
                guessed, _ = mimetypes.guess_type(entry.name)
                mime = guessed or "application/octet-stream"

                row = queries.resources.append(
                    run_id=self._run_id,
                    task_execution_id=self._task_execution_id,
                    kind=resource_kind.value,
                    name=entry.name,
                    mime_type=mime,
                    file_path=str(durable_path),
                    size_bytes=len(content_bytes),
                    error=None,
                    content_hash=content_hash,
                    metadata={"sandbox_origin": sandbox_full_path},
                )
                created.append(RunResourceView.from_row(row))

        return created

    # ------------------------------------------------------------------
    # Non-FS artefact publish -- called from persist_outputs_fn for
    # WorkerOutput.
    # ------------------------------------------------------------------

    def publish_value(
        self,
        *,
        kind: RunResourceKind,
        name: str,
        content: str,
        mime_type: str = "text/plain",
    ) -> RunResourceView | None:
        """Write ``content`` bytes to the blob store and append a row keyed by
        ``name``.  Returns ``None`` if an existing row in this task execution
        already has the same ``content_hash`` (no-op dedup).
        """
        content_bytes = content.encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        prior = queries.resources.find_by_hash(
            task_execution_id=self._task_execution_id,
            content_hash=content_hash,
        )
        if prior is not None:
            return None  # duplicate, no-op

        durable_path = self._write_blob(content_bytes, content_hash)

        row = queries.resources.append(
            run_id=self._run_id,
            task_execution_id=self._task_execution_id,
            kind=kind.value,
            name=name,
            mime_type=mime_type,
            file_path=str(durable_path),
            size_bytes=len(content_bytes),
            error=None,
            content_hash=content_hash,
        )
        return RunResourceView.from_row(row)

    # ------------------------------------------------------------------
    # Blob store -- content-addressed local filesystem.
    # ------------------------------------------------------------------

    def _blob_path(self, content_hash: str) -> Path:
        """Deterministic durable path.  Two-char fanout to keep directory
        sizes reasonable."""
        return self._blob_root / content_hash[:2] / content_hash

    def _write_blob(self, content_bytes: bytes, content_hash: str) -> Path:
        """Write content to the blob store if not already present.  Idempotent."""
        path = self._blob_path(content_hash)
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(content_bytes)
        tmp.rename(path)  # atomic on POSIX
        return path

    async def _list_sandbox_dir(self, path: str) -> list:
        """List directory entries (``EntryInfo`` from e2b).  Missing directory -> ``[]``."""
        try:
            return await self._sandbox.files.list(path)
        except FileNotFoundError:
            return []
