from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID

from ergon_cli.commands.workflow import (
    WorkflowCommandContext,
    WorkflowCommandOutput,
    execute_workflow_command,
)
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.runtime.services.workflow_service import WorkflowService
from sqlmodel import Session


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
) -> Callable[[str], Awaitable[str]]:
    """Build an agent-facing ``workflow(command)`` callable.

    The model supplies only the command string. Run, task, execution, and
    sandbox identity are injected here so prompts cannot escape their current
    run by passing alternate IDs.
    """

    async def workflow(command: str) -> str:
        """Inspect workflow topology/resources or dry-run workflow management commands."""
        if worker_context.node_id is None:
            raise ValueError("workflow tool requires WorkerContext.node_id")

        output = execute_command(
            command,
            context=WorkflowCommandContext(
                run_id=worker_context.run_id,
                node_id=worker_context.node_id,
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

    return workflow
