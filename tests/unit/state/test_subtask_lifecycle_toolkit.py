"""Unit tests for SubtaskLifecycleToolkit pydantic-ai tool closures."""

from uuid import uuid4

import pytest

from ergon_builtins.tools.subtask_lifecycle_toolkit import (
    SubtaskLifecycleToolkit,
    ToolFailure,
)


def _make_toolkit() -> SubtaskLifecycleToolkit:
    return SubtaskLifecycleToolkit(
        run_id=uuid4(),
        parent_node_id=uuid4(),
        sandbox_id="test-sandbox",
    )


@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("cancel_task", ("not-a-uuid",)),
        ("refine_task", ("not-a-uuid", "new description")),
        ("restart_task", ("not-a-uuid",)),
    ],
)
async def test_invalid_uuid_returns_error(tool_name: str, args: tuple) -> None:
    tools = _make_toolkit().get_tools()
    tool = next(t for t in tools if t.__name__ == tool_name)
    result = await tool(*args)
    assert isinstance(result, ToolFailure)
    assert result.kind == "failure"
    error_lower = result.error.lower()
    assert (
        "not-a-uuid" in result.error
        or "invalid" in error_lower
        or "badly formed" in error_lower
        or "hexadecimal" in error_lower
    )


def test_tools_have_correct_function_names() -> None:
    toolkit = _make_toolkit()
    tools = toolkit.get_tools()
    expected_names = [
        "add_subtask",
        "plan_subtasks",
        "cancel_task",
        "refine_task",
        "restart_task",
        "list_subtasks",
        "get_subtask",
        "bash",
    ]
    actual_names = [t.__name__ for t in tools]
    assert actual_names == expected_names
