from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import uuid4

import pytest

from ergon_builtins.tools.workflow_command_adapter import (
    WorkflowCommandContext,
    WorkflowCommandOutput,
    execute_workflow_command,
)
from ergon_builtins.tools.workflow_cli_tool import make_workflow_cli_tool
from ergon_builtins.workers.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetState,
)
from ergon_core.api import Sandbox, Task, Worker, WorkerContext, WorkerOutput, WorkerStreamItem
from ergon_core.api.worker.results import SpawnedTaskHandle
from ergon_core.core.application.runtime.models import GraphTaskRef


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _ResourceService:
    pass


def _worker_context() -> WorkerContext:
    return WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sandbox",
        task_mgmt=object(),
        task_inspect=object(),
        resource_service=_ResourceService(),
        session_factory=_Session,
    )


class _ToySandbox(Sandbox):
    async def provision(self) -> None:
        pass

    async def _bind_runtime(self, sandbox_id: str) -> None:
        pass


class _ToyWorker(Worker):
    type_slug: ClassVar[str] = "toy-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output=f"completed {task.task_slug}")


def _parent_task() -> Task:
    return Task(
        task_slug="parent",
        instance_key="sample-1",
        description="Parent task",
        worker=_ToyWorker(name="toy", model="test:none"),
        sandbox=_ToySandbox(),
        evaluators=(),
    )


@pytest.mark.asyncio
async def test_workflow_tool_injects_worker_context() -> None:
    context = _worker_context()
    seen = {}

    def execute(command, *, context, worker_context, session_factory, service):
        seen["command"] = command
        seen["context"] = context
        seen["worker_context"] = worker_context

        return WorkflowCommandOutput(stdout="ok")

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=context.task_id,
        benchmark_type="researchrubrics",
        execute_command=execute,
    )

    assert await workflow("inspect task-tree") == "ok"
    assert seen["command"] == "inspect task-tree"
    assert seen["context"].run_id == context.run_id
    assert seen["context"].task_id == context.task_id
    assert seen["context"].execution_id == context.execution_id
    assert seen["context"].sandbox_task_key == context.task_id
    assert seen["context"].benchmark_type == "researchrubrics"
    assert seen["worker_context"] is context


@pytest.mark.asyncio
async def test_workflow_tool_reports_nonzero_exit() -> None:
    context = _worker_context()

    def execute(command, *, context, worker_context, session_factory, service):
        return WorkflowCommandOutput(stdout="", stderr="bad command", exit_code=2)

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=context.task_id,
        benchmark_type="researchrubrics",
        execute_command=execute,
    )

    assert await workflow("inspect nope") == "workflow exited 2: bad command"


@pytest.mark.asyncio
async def test_workflow_tool_accepts_async_executor_inside_event_loop() -> None:
    context = _worker_context()

    async def execute(command, *, context, worker_context, session_factory, service):
        assert command.startswith("inspect task-tree")
        return WorkflowCommandOutput(stdout="created")

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=context.task_id,
        benchmark_type="researchrubrics",
        execute_command=execute,
    )

    assert await workflow("inspect task-tree") == "created"


@pytest.mark.asyncio
async def test_workflow_adapter_add_subtask_spawns_object_bound_child() -> None:
    parent_task = _parent_task()
    spawned = {}

    class TaskManagement:
        async def spawn_dynamic_task(self, *, run_id, parent_task_id, task, depends_on=()):
            spawned["run_id"] = run_id
            spawned["parent_task_id"] = parent_task_id
            spawned["task"] = task
            spawned["depends_on"] = depends_on
            return SpawnedTaskHandle(task_id=uuid4())

    worker_context = WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sandbox",
        task_mgmt=TaskManagement(),
        task_inspect=object(),
        resource_service=_ResourceService(),
        session_factory=_Session,
    )

    class Row:
        task_json = parent_task.model_dump(mode="json")

    class Result:
        def one(self):
            return Row()

    class Session:
        def exec(self, statement):
            return Result()

        def close(self):
            pass

    output = await execute_workflow_command(
        "manage add-subtask --task-slug child --description 'Child task' --format json",
        context=WorkflowCommandContext(
            run_id=worker_context.run_id,
            task_id=worker_context.task_id,
            execution_id=worker_context.execution_id,
            sandbox_task_key=worker_context.task_id,
            benchmark_type="researchrubrics",
        ),
        worker_context=worker_context,
        session_factory=Session,
    )

    assert output.exit_code == 0
    assert "child" in output.stdout
    assert spawned["run_id"] == worker_context.run_id
    assert spawned["parent_task_id"] == worker_context.task_id
    assert spawned["task"].task_slug == "child"
    assert spawned["task"].description == "Child task"
    assert spawned["task"].parent_task_slug == "parent"
    assert spawned["task"].worker.type_slug == "toy-worker"
    assert spawned["depends_on"] == ()


@pytest.mark.asyncio
async def test_workflow_adapter_preserves_task_tree_wait_seconds() -> None:
    worker_context = _worker_context()
    child_id = uuid4()

    class Service:
        def __init__(self) -> None:
            self.wait_observed = False

        def list_tasks(self, session, *, run_id, parent_task_id=None):
            self.wait_observed = True
            return [
                GraphTaskRef(
                    task_id=child_id,
                    task_slug="child",
                    status="completed",
                    level=1,
                    parent_task_id=worker_context.task_id,
                    assigned_worker_slug="toy-worker",
                    description="Child task",
                )
            ]

    service = Service()
    output = await execute_workflow_command(
        "inspect task-tree --wait-seconds 0.1 --format json",
        context=WorkflowCommandContext(
            run_id=worker_context.run_id,
            task_id=worker_context.task_id,
            execution_id=worker_context.execution_id,
            sandbox_task_key=worker_context.task_id,
            benchmark_type="researchrubrics",
        ),
        worker_context=worker_context,
        session_factory=_Session,
        service=service,
    )

    assert output.exit_code == 0
    assert service.wait_observed is True
    assert str(child_id) in output.stdout


@pytest.mark.asyncio
async def test_budgeted_workflow_tool_returns_structured_exhaustion() -> None:
    context = _worker_context()
    calls = 0

    def execute(command, *, context, worker_context, session_factory, service):
        nonlocal calls
        calls += 1
        return WorkflowCommandOutput(stdout="ok")

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=context.task_id,
        benchmark_type="researchrubrics",
        execute_command=execute,
        budgeted=True,
    )
    deps = AgentToolBudgetDeps(
        tool_budget=AgentToolBudgetState(
            max_workflow_tool_calls=1,
            max_other_tool_calls=1,
        ),
    )
    ctx = type("Ctx", (), {"deps": deps})()

    first = await workflow(ctx, "inspect task-tree")
    exhausted = await workflow(ctx, "inspect task-tree")

    assert first == "ok"
    assert exhausted.status == "TOOL_BUDGET_EXHAUSTED"
    assert exhausted.reason == "workflow tool budget reached"
    assert calls == 1
