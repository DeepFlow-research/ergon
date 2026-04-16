"""Manager-researcher worker for dynamic delegation.

Builds its own delegation tools from WorkerContext at execution time.
No special cases needed in worker_execute_fn.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api.generation import GenerationTurn
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext

from ergon_builtins.tools.task_management_toolkit import (
    TaskManagementToolkit,
)
from ergon_builtins.workers.baselines.react_worker import ReActWorker

_SYSTEM_PROMPT = (
    "You are a manager agent that delegates work to researcher sub-agents. "
    "You have access to delegation tools:\n"
    "- add_task(description, worker_binding_key): Spawn a new researcher "
    "sub-agent to work on a sub-question. Returns a node_id.\n"
    "- abandon_task(node_id): Cancel a stalling sub-agent.\n"
    "- refine_task(node_id, new_description): Update a pending sub-agent's "
    "task description.\n\n"
    "You MUST use add_task to delegate work to researcher sub-agents. "
    "Do NOT try to answer the research question yourself. "
    "Break the question into sub-questions, spawn a researcher for each one "
    "using add_task, then provide your final synthesis."
)


class ManagerResearcherWorker(ReActWorker):
    """Manager agent that delegates to researcher sub-agents.

    Builds delegation tools (add_task, abandon_task, refine_task) from
    the WorkerContext it receives in execute(). The tools close over
    run_id, definition_id, and node_id so the LLM never sees infra IDs.
    """

    type_slug: ClassVar[str] = "manager-researcher"

    def __init__(
        self,
        *,
        name: str,
        model: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            tools=[],
            system_prompt=_SYSTEM_PROMPT,
            max_iterations=20,
        )

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        if context.node_id is not None:
            toolkit = TaskManagementToolkit(
                run_id=context.run_id,
                definition_id=context.definition_id or context.run_id,
                parent_node_id=context.node_id,
            )
            self.tools = toolkit.get_tools()

        async for turn in super().execute(task, context=context):
            yield turn
