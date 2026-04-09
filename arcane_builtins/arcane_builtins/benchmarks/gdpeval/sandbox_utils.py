"""Helpers for pulling GDP output files from the sandbox.

Provides convenience wrappers around :class:`BaseSandboxManager` for
the common GDPEval patterns: downloading final output files,
listing workspace contents, and reading specific output artifacts.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from h_arcane.core.providers.sandbox.manager import BaseSandboxManager

logger = logging.getLogger(__name__)

FINAL_OUTPUT_DIR = "/workspace/final_output"
SCRATCHPAD_DIR = "/workspace/scratchpad"
INPUTS_DIR = "/inputs"

# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class SandboxFileInfo(BaseModel):
    """Metadata about a file inside the sandbox."""

    sandbox_path: str
    size_bytes: int | None = None
    extension: str = ""  # slopcop: ignore[no-str-empty-default]

class GDPOutputBundle(BaseModel):
    """Collection of downloaded output files for a GDP task."""

    task_id: str
    files: list[SandboxFileInfo] = Field(default_factory=list)
    local_dir: str | None = None
    error: str | None = None

# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------

async def list_output_files(
    sandbox_manager: "BaseSandboxManager",
    task_id: UUID,
) -> list[str]:
    """List all files in ``/workspace/final_output``."""
    try:
        return await sandbox_manager.list_files(task_id, FINAL_OUTPUT_DIR)
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        logger.warning("Failed to list output files for task %s: %s", task_id, exc)
        return []

async def download_output_bundle(
    sandbox_manager: "BaseSandboxManager",
    task_id: UUID,
    local_dir: Path,
) -> GDPOutputBundle:
    """Download all final-output files into *local_dir*.

    Returns a :class:`GDPOutputBundle` summarising what was fetched.
    """
    local_dir.mkdir(parents=True, exist_ok=True)
    bundle = GDPOutputBundle(task_id=str(task_id), local_dir=str(local_dir))

    try:
        remote_files = await list_output_files(sandbox_manager, task_id)
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        bundle.error = str(exc)
        return bundle

    for remote_path in remote_files:
        try:
            content = await sandbox_manager.download_file(task_id, remote_path)
            filename = Path(remote_path).name
            dest = local_dir / filename
            dest.write_bytes(content)
            bundle.files.append(
                SandboxFileInfo(
                    sandbox_path=remote_path,
                    size_bytes=len(content),
                    extension=Path(filename).suffix,
                )
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            logger.warning(
                "Failed to download %s for task %s: %s",
                remote_path,
                task_id,
                exc,
            )

    return bundle

async def read_output_text(
    sandbox_manager: "BaseSandboxManager",
    task_id: UUID,
    filename: str,
) -> str | None:
    """Read a single text file from the final-output directory.

    Returns ``None`` when the file doesn't exist or isn't readable.
    """
    remote_path = f"{FINAL_OUTPUT_DIR}/{filename}"
    try:
        content = await sandbox_manager.download_file(task_id, remote_path)
        return content.decode("utf-8", errors="replace")
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        logger.debug("Could not read %s for task %s: %s", remote_path, task_id, exc)
        return None

async def upload_reference_files(
    sandbox_manager: "BaseSandboxManager",
    task_id: UUID,
    reference_files: list[Path],
) -> int:
    """Upload reference / input files into ``/inputs/``.

    Returns the number of files successfully uploaded.
    """
    uploaded = 0
    for file_path in reference_files:
        if not file_path.is_file():
            logger.warning("Reference file does not exist: %s", file_path)
            continue
        try:
            remote_path = f"{INPUTS_DIR}/{file_path.name}"
            await sandbox_manager.upload_file(task_id, str(file_path), remote_path)
            uploaded += 1
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to upload %s: %s", file_path, exc)
    return uploaded
