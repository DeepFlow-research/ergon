from uuid import uuid4

import pytest

from ergon_builtins.toolkits.subagents.toolkit import (
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
        if task_id != self.allowed_id:
            raise RuntimeError("not contained")

    async def refine_task(self, task_id, *, description):
        self.calls.append(("refine", task_id, description))
        if task_id != self.allowed_id:
            raise RuntimeError("not contained")

    async def restart_task(self, task_id):
        self.calls.append(("restart", task_id))
        if task_id != self.allowed_id:
            raise RuntimeError("not contained")

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

    await cancel_task(str(context.allowed_id))
    await refine_task(str(context.allowed_id), "new description")
    await restart_task(str(context.allowed_id))
    listed = await list_subtasks()

    assert isinstance(listed, ListSubtasksToolSuccess)
    assert [call[0] for call in context.calls] == ["cancel", "refine", "restart", "subtasks"]


@pytest.mark.asyncio
async def test_worker_toolkit_returns_failure_when_context_blocks_target() -> None:
    context = _FakeContext()
    toolkit = SubtaskLifecycleToolkit(context=context)
    tools = {tool.__name__: tool for tool in toolkit.get_tools()}
    blocked_id = str(uuid4())

    results = [
        await tools["cancel_task"](blocked_id),
        await tools["refine_task"](blocked_id, "new description"),
        await tools["restart_task"](blocked_id),
        await tools["get_subtask"](blocked_id),
    ]

    assert all(isinstance(result, ToolFailure) for result in results)
    assert all("not contained" in result.error for result in results)
