"""Unit tests for SubtaskLifecycleToolkit pydantic-ai tool closures."""

from collections.abc import AsyncGenerator
from typing import Any, cast
from uuid import uuid4

import pytest
from ergon_core.api import EmptyTaskPayload, Sandbox, Task, WorkerOutput
from ergon_core.core.shared.context_parts import ContextPartChunk
from ergon_core.api.worker import SpawnedTaskHandle
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.worker import Worker
from ergon_builtins.toolkits.subagents.toolkit import (
    SubtaskLifecycleToolkit,
    ToolFailure,
)
from ergon_core.core.infrastructure.dashboard.provider import (
    init_dashboard_emitter,
    reset_dashboard_emitter,
)


@pytest.fixture(autouse=True)
def _dashboard_emitter() -> None:
    init_dashboard_emitter(enabled=False)
    yield
    reset_dashboard_emitter()


def _make_toolkit() -> SubtaskLifecycleToolkit:
    return SubtaskLifecycleToolkit(context=cast("WorkerContext", _FakeWorkerContext()))


class _FakeWorkerContext:
    sandbox_id = "test-sandbox"

    def __init__(self) -> None:
        self.spawned: list[tuple[Task, tuple]] = []

    async def spawn_task(
        self,
        task: Task,
        *,
        depends_on: tuple = (),
    ) -> SpawnedTaskHandle:
        self.spawned.append((task, depends_on))
        return SpawnedTaskHandle(task_id=uuid4())

    async def cancel_task(self, task_id):
        return None

    async def refine_task(self, task_id, *, description: str):
        return None

    async def restart_task(self, task_id):
        return SpawnedTaskHandle(task_id=task_id)

    async def subtasks(self):
        return ()

    async def get_task(self, task_id):
        return {
            "node_id": task_id,
            "task_slug": "child",
            "description": "child",
            "status": "pending",
            "depends_on": [],
            "output": None,
            "error": None,
        }


def test_subtask_lifecycle_toolkit_requires_worker_context() -> None:
    kwargs: dict[str, object] = {
        "run_id": uuid4(),
        "parent_task_id": uuid4(),
        "sandbox_id": "test-sandbox",
    }
    with pytest.raises(TypeError, match="unexpected keyword argument 'run_id'"):
        SubtaskLifecycleToolkit(**kwargs)


async def test_add_subtask_accepts_object_bound_task() -> None:
    context = _FakeWorkerContext()
    toolkit = SubtaskLifecycleToolkit(context=context)
    add_subtask = next(t for t in toolkit.get_tools() if t.__name__ == "add_subtask")
    task = Task(
        task_slug="child",
        instance_key="sample",
        description="Object-bound child",
        task_payload=EmptyTaskPayload(),
        worker=_NoopWorker(name="noop", model="test:none"),
        sandbox=_NoopSandbox(),
        evaluators=(),
    )

    result = await add_subtask(task)

    assert result.kind == "success"
    assert context.spawned == [(task, ())]


class _NoopWorker(Worker):
    type_slug = "noop"

    async def execute(  # ty: ignore[invalid-method-override]
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[ContextPartChunk | WorkerOutput, None]:
        yield WorkerOutput(output=task.task_slug, success=True)


class _NoopSandbox(Sandbox):
    async def provision(self) -> None:
        return None

    async def _bind_runtime(self, sandbox_id: str) -> None:
        return None


def _make_legacy_admin_toolkit() -> SubtaskLifecycleToolkit:
    kwargs: dict[str, Any] = {
        "run_id": uuid4(),
        "parent_task_id": uuid4(),
        "sandbox_id": "test-sandbox",
    }
    return SubtaskLifecycleToolkit(**kwargs)


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
