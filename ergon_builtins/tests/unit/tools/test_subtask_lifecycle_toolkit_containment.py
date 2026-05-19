from uuid import uuid4

import pytest

from ergon_builtins.tools.subtask_lifecycle_toolkit import (
    ListSubtasksToolSuccess,
    SubtaskLifecycleToolkit,
    ToolFailure,
)


class _FakeContext:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.allowed_id = uuid4()
        self.sandbox_id = "sbx-test"

    async def cancel_task(self, task_id):
        self.calls.append(("cancel", task_id))

    async def refine_task(self, task_id, *, description):
        self.calls.append(("refine", task_id, description))

    async def restart_task(self, task_id):
        self.calls.append(("restart", task_id))

    async def subtasks(self):
        self.calls.append(("subtasks",))
        return []

    async def get_task(self, task_id):
        self.calls.append(("get", task_id))
        if task_id != self.allowed_id:
            raise RuntimeError("not contained")
        return {
            "node_id": task_id,
            "task_slug": "child",
            "description": "child",
            "status": "pending",
            "depends_on": [],
            "output": None,
            "error": None,
        }


@pytest.mark.asyncio
async def test_worker_toolkit_routes_lifecycle_calls_through_worker_context() -> None:
    context = _FakeContext()
    toolkit = SubtaskLifecycleToolkit(context=context)

    tools = toolkit.get_tools()
    cancel_task = next(tool for tool in tools if tool.__name__ == "cancel_task")
    refine_task = next(tool for tool in tools if tool.__name__ == "refine_task")
    restart_task = next(tool for tool in tools if tool.__name__ == "restart_task")
    list_subtasks = next(tool for tool in tools if tool.__name__ == "list_subtasks")

    target_id = uuid4()
    await cancel_task(str(target_id))
    await refine_task(str(target_id), "new description")
    await restart_task(str(target_id))
    listed = await list_subtasks()

    assert isinstance(listed, ListSubtasksToolSuccess)
    assert [call[0] for call in context.calls] == ["cancel", "refine", "restart", "subtasks"]


@pytest.mark.asyncio
async def test_worker_toolkit_returns_failure_when_context_blocks_target() -> None:
    context = _FakeContext()
    toolkit = SubtaskLifecycleToolkit(context=context)
    get_subtask = next(tool for tool in toolkit.get_tools() if tool.__name__ == "get_subtask")

    result = await get_subtask(str(uuid4()))

    assert isinstance(result, ToolFailure)
    assert "not contained" in result.error
