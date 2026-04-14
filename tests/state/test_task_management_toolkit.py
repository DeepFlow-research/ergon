"""Unit tests for TaskManagementToolkit pydantic-ai tool closures."""

import asyncio
from uuid import uuid4

from ergon_builtins.tools.task_management_toolkit import TaskManagementToolkit


def test_get_tools_returns_three_callables() -> None:
    toolkit = TaskManagementToolkit(
        run_id=uuid4(),
        definition_id=uuid4(),
        parent_node_id=uuid4(),
    )
    tools = toolkit.get_tools()
    assert len(tools) == 3
    assert all(callable(t) for t in tools)


def test_add_task_tool_is_async_callable() -> None:
    toolkit = TaskManagementToolkit(
        run_id=uuid4(),
        definition_id=uuid4(),
        parent_node_id=uuid4(),
    )
    tools = toolkit.get_tools()
    assert asyncio.iscoroutinefunction(tools[0])


async def test_abandon_task_handles_invalid_uuid_gracefully() -> None:
    toolkit = TaskManagementToolkit(
        run_id=uuid4(),
        definition_id=uuid4(),
        parent_node_id=uuid4(),
    )
    tools = toolkit.get_tools()
    abandon = tools[1]
    result = await abandon("not-a-uuid")
    assert result["success"] is False
    assert "error" in result
    assert isinstance(result["error"], str)
    assert len(result["error"]) > 0


async def test_refine_task_handles_invalid_uuid_gracefully() -> None:
    toolkit = TaskManagementToolkit(
        run_id=uuid4(),
        definition_id=uuid4(),
        parent_node_id=uuid4(),
    )
    tools = toolkit.get_tools()
    refine = tools[2]
    result = await refine("not-a-uuid", "new desc")
    assert result["success"] is False
    assert "error" in result
    assert isinstance(result["error"], str)
    assert len(result["error"]) > 0


def test_tools_have_correct_function_names() -> None:
    toolkit = TaskManagementToolkit(
        run_id=uuid4(),
        definition_id=uuid4(),
        parent_node_id=uuid4(),
    )
    tools = toolkit.get_tools()
    assert tools[0].__name__ == "add_task"
    assert tools[1].__name__ == "abandon_task"
    assert tools[2].__name__ == "refine_task"
