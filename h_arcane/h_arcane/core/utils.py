"""Shared utility functions."""

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

mimetypes.add_type("text/markdown", ".md")

T = TypeVar("T")


def utcnow() -> datetime:
    """Return current UTC time as a naive datetime for Postgres TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def require_not_none(value: T | None, error_msg: str) -> T:
    if value is None:
        raise ValueError(error_msg)
    return value


def get_mime_type(file_path: Path | str) -> str:
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"
