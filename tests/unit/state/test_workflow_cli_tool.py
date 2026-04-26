from uuid import uuid4

import pytest
from ergon_builtins.tools.workflow_cli_tool import make_workflow_cli_tool
from ergon_core.api.worker_context import WorkerContext


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
