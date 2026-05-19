"""Application ports for sandbox resource publication adapters."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol


class SandboxFileReader(Protocol):
    """Reads publishable files from a sandbox filesystem."""

    async def list_sandbox_dir(self, path: str) -> Sequence[Any]: ...

    async def read_sandbox_file(self, path: str) -> bytes | str: ...

    def entry_name(self, entry: Any) -> str: ...

    def entry_path(self, sandbox_dir: str, entry: Any) -> str: ...


class ResourceBlobWriter(Protocol):
    """Writes content-addressed resource blobs."""

    def blob_path(self, content_hash: str) -> Path | str: ...

    def write_blob(self, content_bytes: bytes, content_hash: str) -> Path | str: ...
