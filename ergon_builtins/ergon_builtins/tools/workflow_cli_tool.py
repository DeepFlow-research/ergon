import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from ergon_cli.commands.workflow import (
    WorkflowCommandContext,
    WorkflowCommandOutput,
    execute_workflow_command,
)
from ergon_core.api import WorkerContext
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.workflows.service import WorkflowService
from pydantic_ai import RunContext
from sqlmodel import Session

from ergon_builtins.workers.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetExhaustedResult,
)


class WorkflowCommandExecutor(Protocol):
    def __call__(
        self,
        command: str,
        *,
        context: WorkflowCommandContext,
        session_factory: Callable[[], Session],
        service: WorkflowService,
    ) -> WorkflowCommandOutput: ...


def make_workflow_cli_tool(
    *,
    worker_context: WorkerContext,
    sandbox_task_key: UUID,
    benchmark_type: str,
    execute_command: WorkflowCommandExecutor = execute_workflow_command,
    session_factory: Callable[[], Session] = get_session,
    service_factory: Callable[[], WorkflowService] = WorkflowService,
    budgeted: bool = False,
) -> Callable[..., Awaitable[Any]]:  # slopcop: ignore[no-typing-any]
    """Build an agent-facing ``workflow(command)`` callable.

    The model supplies only the command string. Run, task, execution, and
    sandbox identity are injected here so prompts cannot escape their current
    run by passing alternate IDs.
    """

    async def run_command(command: str) -> str:
        if worker_context.task_id is None:
            raise ValueError("workflow tool requires WorkerContext.task_id")

        output = await asyncio.to_thread(
            execute_command,
            command,
            context=WorkflowCommandContext(
                run_id=worker_context.run_id,
                node_id=worker_context.task_id,
                execution_id=worker_context.execution_id,
                sandbox_task_key=sandbox_task_key,
                benchmark_type=benchmark_type,
            ),
            session_factory=session_factory,
            service=service_factory(),
        )
        if output.exit_code != 0:
            detail = output.stderr or output.stdout
            return f"workflow exited {output.exit_code}: {detail}".strip()
        if output.stderr:
            return f"{output.stdout}\n\nstderr:\n{output.stderr}".strip()
        return output.stdout

    if budgeted:

        async def workflow(
            ctx: RunContext[AgentToolBudgetDeps],
            command: str,
        ) -> str | AgentToolBudgetExhaustedResult:
            """Inspect workflow topology/resources or dry-run workflow management commands."""
            tool_budget = ctx.deps.tool_budget
            if tool_budget.increment("workflow", "workflow") > tool_budget.max_workflow_tool_calls:
                return tool_budget.exhausted_result("workflow tool budget reached")
            return await run_command(command)

        return workflow

    async def workflow(command: str) -> str:
        """Inspect workflow topology/resources or dry-run workflow management commands."""
        return await run_command(command)

    return workflow
