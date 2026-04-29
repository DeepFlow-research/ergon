from uuid import uuid4

import pytest
from ergon_builtins.tools.workflow_cli_tool import make_workflow_cli_tool
from ergon_builtins.workers.baselines.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetState,
)
from ergon_cli.commands.workflow import WorkflowCommandOutput, execute_workflow_command
from ergon_core.api.worker import WorkerContext


@pytest.mark.asyncio
async def test_workflow_tool_injects_worker_context() -> None:
    context = WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sandbox",
        node_id=uuid4(),
    )
    seen = {}

    def execute(command, *, context, session_factory, service):
        seen["command"] = command
        seen["context"] = context

        class Output:
            stdout = "ok"
            stderr = ""
            exit_code = 0

        return Output()

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=context.task_id,
        benchmark_type="researchrubrics",
        execute_command=execute,
    )

    assert await workflow("inspect task-tree") == "ok"
    assert seen["command"] == "inspect task-tree"
    assert seen["context"].run_id == context.run_id
    assert seen["context"].node_id == context.node_id
    assert seen["context"].execution_id == context.execution_id
    assert seen["context"].sandbox_task_key == context.task_id
    assert seen["context"].benchmark_type == "researchrubrics"


@pytest.mark.asyncio
async def test_workflow_tool_reports_nonzero_exit() -> None:
    context = WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sandbox",
        node_id=uuid4(),
    )

    def execute(command, *, context, session_factory, service):
        class Output:
            stdout = ""
            stderr = "bad command"
            exit_code = 2

        return Output()

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=context.task_id,
        benchmark_type="researchrubrics",
        execute_command=execute,
    )

    assert await workflow("inspect nope") == "workflow exited 2: bad command"


@pytest.mark.asyncio
async def test_workflow_tool_can_run_manage_commands_inside_event_loop() -> None:
    context = WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sandbox",
        node_id=uuid4(),
    )

    def execute(command, *, context, session_factory, service):
        assert command.startswith("manage add-task")
        return WorkflowCommandOutput(stdout="created")

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=context.task_id,
        benchmark_type="researchrubrics",
        execute_command=execute,
    )

    assert await workflow("manage add-task --task-slug source --worker worker --description x") == (
        "created"
    )


@pytest.mark.asyncio
async def test_workflow_tool_default_executor_handles_async_manage_bridge() -> None:
    context = WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sandbox",
        node_id=uuid4(),
    )

    class Session:
        def close(self):
            pass

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=context.task_id,
        benchmark_type="researchrubrics",
        execute_command=execute_workflow_command,
        session_factory=Session,
    )

    result = await workflow(
        "manage add-task --task-slug source --worker worker --description x --dry-run"
    )

    assert "Graph lifecycle command validated" in result


@pytest.mark.asyncio
async def test_budgeted_workflow_tool_returns_structured_exhaustion() -> None:
    context = WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sandbox",
        node_id=uuid4(),
    )
    calls = 0

    def execute(command, *, context, session_factory, service):
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
