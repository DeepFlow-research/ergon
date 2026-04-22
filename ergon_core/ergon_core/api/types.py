# ergon_core/ergon_core/api/types.py
"""Shared type aliases for the public API surface."""

from typing import Any

type Tool = Any  # slopcop: ignore[no-typing-any]
"""Framework-agnostic tool carrier.

Intentionally unconstrained so workers can integrate with any agent
framework. ``ReActWorker`` passes these through to pydantic-ai's
``Agent(tools=...)``; nothing in our code enforces a structural protocol.
If we ever pin to pydantic-ai, tighten this to
``pydantic_ai.tools.Tool | Callable[..., Any]``.
"""

__all__ = ["Tool"]
