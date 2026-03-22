"""Private helpers for sandbox instrumentation."""

from typing import Any

from h_arcane.core._internal.infrastructure.tracing import truncate_text


def coerce_text(value: Any) -> str | None:
    """Best-effort conversion of sandbox output values to text."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return "\n".join(coerce_text(item) or "" for item in value)
    return str(value)


def bytes_length(value: Any) -> int | None:
    """Approximate payload size for file operations."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, bytearray):
        return len(value)
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    return None


def preview_python_code(code: str, max_length: int = 120) -> str:
    """Generate a short, single-line preview for Python execution."""
    lines = [line.strip() for line in code.splitlines() if line.strip()]
    preview = lines[0] if lines else "<empty>"
    truncated = truncate_text(preview, max_length) or "<empty>"
    return truncated.replace("\n", " ")
