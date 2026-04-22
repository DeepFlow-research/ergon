"""Manager-researcher worker for dynamic delegation.

Builds its own delegation tools from WorkerContext at execution time.
No special cases needed in worker_execute_fn.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import UUID

from ergon_core.api.generation import GenerationTurn
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext

from ergon_builtins.tools.subtask_lifecycle_toolkit import (
    build_subtask_lifecycle_tools,
)
from ergon_builtins.workers.baselines.react_worker import ReActWorker

_SYSTEM_PROMPT = (
    "You are a manager agent that delegates work to researcher sub-agents. "
    "You have access to delegation tools:\n"
    "- add_subtask(task_slug, description, assigned_worker_slug, depends_on): "
    "Spawn a new researcher sub-agent to work on a sub-question. Choose a "
    "short kebab-case task_slug (e.g. 'subq-rl-history') — it is persisted "
    "verbatim and used to identify this node. Returns a node_id.\n"
    "- plan_subtasks(subtasks): Atomically create a sub-DAG of subtasks.\n"
    "- cancel_task(node_id): Cancel a stalling sub-agent.\n"
    "- refine_task(node_id, new_description): Update a pending sub-agent's "
    "task description.\n"
    "- list_subtasks(): List status and output of every direct subtask.\n"
    "- get_subtask(node_id): Get full details for one subtask.\n"
    "- bash(command): Run a shell command in the sandbox (e.g. sleep).\n\n"
    "You MUST use add_subtask to delegate work to researcher sub-agents. "
    "Do NOT try to answer the research question yourself. "
    "Break the question into sub-questions, spawn a researcher for each one "
    "using add_subtask, then provide your final synthesis."
)


class ManagerResearcherWorker(ReActWorker):
    """Manager agent that delegates to researcher sub-agents.

    Builds delegation tools (add_subtask, plan_subtasks, cancel_task,
    refine_task, list_subtasks, get_subtask, bash) from the WorkerContext
    it receives in execute(). The tools close over run_id and node_id
    so the LLM never sees infra IDs.
    """

    type_slug: ClassVar[str] = "manager-researcher"

    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        task_id: UUID,
        sandbox_id: str,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            task_id=task_id,
            sandbox_id=sandbox_id,
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
        if context.node_id is None:
            raise RuntimeError("ManagerResearcherWorker requires WorkerContext.node_id")

        self.tools = build_subtask_lifecycle_tools(
            run_id=context.run_id,
            parent_node_id=context.node_id,
            sandbox_id=context.sandbox_id,
        )

        async for turn in super().execute(task, context=context):
            yield turn
