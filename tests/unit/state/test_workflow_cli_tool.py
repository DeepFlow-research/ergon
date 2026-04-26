from uuid import uuid4

import pytest
from ergon_builtins.tools.workflow_cli_tool import make_workflow_cli_tool
from ergon_core.api.worker_context import WorkerContext


@pytest.mark.asyncio
async def test_workflow_tool_injects_worker_context() -> None:
    task_key = uuid4()
    context = WorkerContext(
        run_id=uuid4(),
        task_id=task_key,
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
        sandbox_task_key=task_key,
        benchmark_type="researchrubrics",
        execute_command=execute,
    )

    assert await workflow("inspect task-tree") == "ok"
    assert seen["command"] == "inspect task-tree"
    assert seen["context"].run_id == context.run_id
    assert seen["context"].node_id == context.node_id
    assert seen["context"].execution_id == context.execution_id
    assert seen["context"].sandbox_task_key == task_key
    assert seen["context"].benchmark_type == "researchrubrics"


@pytest.mark.asyncio
async def test_workflow_tool_reports_nonzero_exit() -> None:
    task_key = uuid4()
    context = WorkerContext(
        run_id=uuid4(),
        task_id=task_key,
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
        sandbox_task_key=task_key,
        benchmark_type="researchrubrics",
        execute_command=execute,
    )

    assert await workflow("inspect nope") == "workflow exited 2: bad command"


@pytest.mark.asyncio
async def test_leaf_workflow_tool_rejects_graph_edit_commands() -> None:
    task_key = uuid4()
    context = WorkerContext(
        run_id=uuid4(),
        task_id=task_key,
        execution_id=uuid4(),
        sandbox_id="sandbox",
        node_id=uuid4(),
    )

    def execute(command, *, context, session_factory, service):
        raise AssertionError("denied commands must not reach executor")

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=task_key,
        benchmark_type="researchrubrics",
        execute_command=execute,
    )

    result = await workflow("manage add-task --task-slug child --description Child --worker worker")

    assert result.startswith("workflow denied:")
    assert "manager-capable" in result


@pytest.mark.asyncio
async def test_manager_workflow_tool_allows_graph_edit_commands() -> None:
    task_key = uuid4()
    context = WorkerContext(
        run_id=uuid4(),
        task_id=task_key,
        execution_id=uuid4(),
        sandbox_id="sandbox",
        node_id=uuid4(),
    )
    seen = {}

    def execute(command, *, context, session_factory, service):
        seen["command"] = command

        class Output:
            stdout = "ok"
            stderr = ""
            exit_code = 0

        return Output()

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=task_key,
        benchmark_type="researchrubrics",
        execute_command=execute,
        manager_capable=True,
    )

    assert await workflow("manage restart-task --task-slug child --dry-run") == "ok"
    assert seen["command"] == "manage restart-task --task-slug child --dry-run"


@pytest.mark.asyncio
async def test_workflow_tool_rejects_multiline_commands() -> None:
    task_key = uuid4()
    context = WorkerContext(
        run_id=uuid4(),
        task_id=task_key,
        execution_id=uuid4(),
        sandbox_id="sandbox",
        node_id=uuid4(),
    )

    def execute(command, *, context, session_factory, service):
        raise AssertionError("multiline commands must not reach executor")

    workflow = make_workflow_cli_tool(
        worker_context=context,
        sandbox_task_key=task_key,
        benchmark_type="researchrubrics",
        execute_command=execute,
        manager_capable=True,
    )

    assert await workflow("inspect task-tree\ninspect next-actions") == (
        "workflow denied: multiline commands are not allowed"
    )
