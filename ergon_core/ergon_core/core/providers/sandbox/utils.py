"""Private helpers for sandbox instrumentation."""

from typing import Any


def coerce_text(value: Any) -> str | None:  # slopcop: ignore[no-typing-any]
    """Best-effort conversion of sandbox output values to text."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return "\n".join(coerce_text(item) or "" for item in value)
    return str(value)


def bytes_length(value: Any) -> int | None:  # slopcop: ignore[no-typing-any]
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


def _truncate(text: str | None, max_length: int) -> str | None:
    if text is None:
        return None
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def preview_python_code(code: str, max_length: int = 120) -> str:
    """Generate a short, single-line preview for Python execution."""
    lines = [line.strip() for line in code.splitlines() if line.strip()]
    preview = lines[0] if lines else "<empty>"
    truncated = _truncate(preview, max_length) or "<empty>"
    return truncated.replace("\n", " ")
