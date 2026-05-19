"""Sandbox filesystem and blob-store adapter for resource publication.

Copies bytes out of an E2B sandbox into a content-addressed blob store on the
local filesystem. Application resource row semantics live in
``RunResourcePublishService``.
"""

import logging
import os
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar
from uuid import UUID

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
from ergon_core.core.application.resources.models import RunResourceView
from ergon_core.core.application.resources.publishing import RunResourcePublishService
from ergon_core.core.persistence.shared.enums import RunResourceKind

logger = logging.getLogger(__name__)

_DEFAULT_BLOB_ROOT = Path(os.environ.get("ERGON_BLOB_ROOT", "/var/ergon/blob"))


class SandboxResourcePublisher:
    """Adapter for reading sandbox files and writing content-addressed blobs.

    ``sync()`` and ``publish_value()`` remain as compatibility helpers, but
    they delegate resource append/dedup decisions to ``RunResourcePublishService``.
    """

    # Default ``(sandbox_path, resource_kind)`` pairs scanned by ``sync()``.
    # Managers that need to publish from additional directories (e.g. a
    # researcher's scratchpad as well as ``final_output/``) pass a custom
    # ``publish_dirs`` to ``__init__``.
    DEFAULT_PUBLISH_DIRS: ClassVar[tuple[tuple[str, RunResourceKind], ...]] = (
        ("/workspace/final_output/", RunResourceKind.REPORT),
    )

    def __init__(
        self,
        *,
        sandbox: AsyncSandbox | Any,  # slopcop: ignore[no-typing-any]
        run_id: UUID,
        task_execution_id: UUID,
        blob_root: Path = _DEFAULT_BLOB_ROOT,
        publish_dirs: tuple[tuple[str, RunResourceKind], ...] | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._run_id = run_id
        self._task_execution_id = task_execution_id
        self._blob_root = blob_root
        self._publish_dirs = publish_dirs if publish_dirs is not None else self.DEFAULT_PUBLISH_DIRS

    @classmethod
    def from_public_sandbox(
        cls,
        *,
        sandbox: Any,  # slopcop: ignore[no-typing-any]
        run_id: UUID,
        task_execution_id: UUID,
        blob_root: Path = _DEFAULT_BLOB_ROOT,
        publish_dirs: tuple[tuple[str, RunResourceKind], ...] | None = None,
    ) -> "SandboxResourcePublisher":
        return cls(
            sandbox=sandbox,
            run_id=run_id,
            task_execution_id=task_execution_id,
            blob_root=blob_root,
            publish_dirs=publish_dirs,
        )

    # ------------------------------------------------------------------
    # Filesystem sync -- called from write-type toolkit methods and from
    # persist_outputs_fn at task end.
    # ------------------------------------------------------------------

    async def sync(self) -> list[RunResourceView]:
        """Publish configured sandbox dirs through the application service."""
        return await RunResourcePublishService().publish_sandbox_files(
            reader=self,
            blob_store=self,
            run_id=self._run_id,
            task_execution_id=self._task_execution_id,
            publish_dirs=self._publish_dirs,
        )

    # ------------------------------------------------------------------
    # Non-FS artefact publish -- used by explicit toolkit calls for values
    # that should appear as task resources.
    # ------------------------------------------------------------------

    def publish_value(
        self,
        *,
        kind: RunResourceKind,
        name: str,
        content: str,
        mime_type: str = "text/plain",
    ) -> RunResourceView | None:
        """Publish explicit value content through the application service."""
        return RunResourcePublishService().publish_value(
            blob_store=self,
            run_id=self._run_id,
            task_execution_id=self._task_execution_id,
            kind=kind,
            name=name,
            content=content,
            mime_type=mime_type,
        )

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

    def blob_path(self, content_hash: str) -> Path:
        return self._blob_path(content_hash)

    def write_blob(self, content_bytes: bytes, content_hash: str) -> Path:
        return self._write_blob(content_bytes, content_hash)

    async def _list_sandbox_dir(self, path: str) -> list:
        """List directory entries (``EntryInfo`` from e2b).  Missing directory -> ``[]``."""
        try:
            # typing: runtime-protocol
            if hasattr(self._sandbox, "files"):  # slopcop: ignore[no-hasattr-getattr]
                return await self._sandbox.files.list(path)
            return await self._sandbox.list_files(path)
        except FileNotFoundError:
            return []

    async def _read_sandbox_file(self, path: str) -> bytes | str:
        # typing: runtime-protocol
        if hasattr(self._sandbox, "files"):  # slopcop: ignore[no-hasattr-getattr]
            return await self._sandbox.files.read(
                path,
                request_timeout=30,
            )
        return await self._sandbox.read_file(path)

    async def list_sandbox_dir(self, path: str) -> list:
        return await self._list_sandbox_dir(path)

    async def read_sandbox_file(self, path: str) -> bytes | str:
        return await self._read_sandbox_file(path)

    def _entry_name(self, entry: Any) -> str:  # slopcop: ignore[no-typing-any]
        # typing: runtime-protocol
        if hasattr(entry, "name"):  # slopcop: ignore[no-hasattr-getattr]
            return str(entry.name)
        return PurePosixPath(str(entry)).name

    def _entry_path(self, sandbox_dir: str, entry: Any) -> str:  # slopcop: ignore[no-typing-any]
        # typing: runtime-protocol
        if hasattr(entry, "name"):  # slopcop: ignore[no-hasattr-getattr]
            return f"{sandbox_dir.rstrip('/')}/{entry.name}"
        entry_path = str(entry)
        if entry_path.startswith("/"):
            return entry_path
        return f"{sandbox_dir.rstrip('/')}/{entry_path}"

    def entry_name(self, entry: Any) -> str:  # slopcop: ignore[no-typing-any]
        return self._entry_name(entry)

    def entry_path(self, sandbox_dir: str, entry: Any) -> str:  # slopcop: ignore[no-typing-any]
        return self._entry_path(sandbox_dir, entry)
