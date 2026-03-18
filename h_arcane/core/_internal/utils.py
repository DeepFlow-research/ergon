"""Shared utility functions."""

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

mimetypes.add_type("text/markdown", ".md")

T = TypeVar("T")


def utcnow() -> datetime:
    """Return current UTC time as a naive datetime (no tzinfo).
    
    Use this instead of datetime.now(timezone.utc) for consistency with
    PostgreSQL TIMESTAMP columns which store naive datetimes.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def require_not_none(value: T | None, error_msg: str) -> T:
    """Raise ValueError if value is None, otherwise return value."""
    if value is None:
        raise ValueError(error_msg)
    return value


def get_mime_type(file_path: Path | str) -> str:
    """Get MIME type for a file path."""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"
