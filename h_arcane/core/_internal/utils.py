"""Shared utility functions."""

import mimetypes
from pathlib import Path
from typing import TypeVar

mimetypes.add_type("text/markdown", ".md")

T = TypeVar("T")


def require_not_none(value: T | None, error_msg: str) -> T:
    """Raise ValueError if value is None, otherwise return value."""
    if value is None:
        raise ValueError(error_msg)
    return value


def get_mime_type(file_path: Path | str) -> str:
    """Get MIME type for a file path."""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"
