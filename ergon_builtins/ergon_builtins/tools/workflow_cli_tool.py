from collections.abc import Awaitable, Callable
import shlex
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

_MANAGER_ONLY_ACTIONS = {
    "add-task",
    "add-edge",
    "update-task-description",
    "restart-task",
    "abandon-task",
}


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
    manager_capable: bool = False,
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
        denial = _denial_reason(command, manager_capable=manager_capable)
        if denial is not None:
            return f"workflow denied: {denial}"

        try:
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
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return f"workflow failed: {type(exc).__name__}: {exc}"
        if output.exit_code != 0:
            detail = output.stderr or output.stdout
            return f"workflow exited {output.exit_code}: {detail}".strip()
        if output.stderr:
            return f"{output.stdout}\n\nstderr:\n{output.stderr}".strip()
        return output.stdout

    return workflow


def _denial_reason(command: str, *, manager_capable: bool) -> str | None:
    if "\n" in command or "\r" in command:
        return "multiline commands are not allowed"
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"could not parse command: {exc}"
    if len(argv) >= 3 and argv[0] == "manage" and argv[1] in _MANAGER_ONLY_ACTIONS:
        if not manager_capable:
            return f"{argv[1]} requires a manager-capable workflow tool"
    return None
