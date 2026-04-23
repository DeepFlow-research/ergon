"""Unit tests for SubtaskLifecycleToolkit pydantic-ai tool closures."""

from uuid import uuid4

from ergon_builtins.tools.subtask_lifecycle_toolkit import SubtaskLifecycleToolkit


def _make_toolkit() -> SubtaskLifecycleToolkit:
    return SubtaskLifecycleToolkit(
        run_id=uuid4(),
        parent_node_id=uuid4(),
        sandbox_id="test-sandbox",
    )


async def test_cancel_task_handles_invalid_uuid_gracefully() -> None:
    toolkit = _make_toolkit()
    tools = toolkit.get_tools()
    cancel = tools[2]
    result = await cancel("not-a-uuid")
    assert result["success"] is False
    assert "error" in result
    assert isinstance(result["error"], str)
    assert len(result["error"]) > 0


async def test_refine_task_handles_invalid_uuid_gracefully() -> None:
    toolkit = _make_toolkit()
    tools = toolkit.get_tools()
    refine = tools[3]
    result = await refine("not-a-uuid", "new desc")
    assert result["success"] is False
    assert "error" in result
    assert isinstance(result["error"], str)
    assert len(result["error"]) > 0


async def test_restart_task_handles_invalid_uuid_gracefully() -> None:
    toolkit = _make_toolkit()
    tools = toolkit.get_tools()
    restart = tools[4]
    result = await restart("not-a-uuid")
    assert result["success"] is False
    assert "error" in result
    assert isinstance(result["error"], str)
    assert len(result["error"]) > 0


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
