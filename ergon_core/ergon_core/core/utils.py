"""Shared utility functions."""

from datetime import datetime, timezone
from typing import TypeVar

T = TypeVar("T")


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def require_not_none(value: T | None, error_msg: str) -> T:
    if value is None:
        raise ValueError(error_msg)
    return value

