"""Strongly-typed models for RunGenerationTurn.tool_calls_json / tool_results_json.

This is the canonical schema for tool call persistence.
Both the write side (react_worker.py) and read side (runs.py, worker_execute.py)
use these models -- no untyped dict access.
"""

from pydantic import BaseModel


class ToolCall(BaseModel):
    """One tool invocation as stored in tool_calls_json."""

    tool_call_id: str
    tool_name: str
    args: dict[str, object] | None = None


class ToolResult(BaseModel):
    """One tool result as stored in tool_results_json."""

    tool_call_id: str
    tool_name: str
    result: str
