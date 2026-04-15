"""ResearchRubrics manager worker.

Builds the manager tool inventory (C2 task management + graph observability)
at execute time from WorkerContext, then delegates to ReActWorker.execute().
The manager spawns researcher sub-agents via add_task and observes their
drafts via the graph toolkit.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api.generation import GenerationTurn
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext

from ergon_builtins.tools.graph_toolkit import ResearchGraphToolkit
from ergon_builtins.tools.task_management_toolkit import (
    TaskManagementToolkit,
)
from ergon_builtins.workers.baselines.react_worker import ReActWorker

_MANAGER_SYSTEM_PROMPT = (
    "You are a research manager agent that delegates work to researcher "
    "sub-agents and synthesises their findings into a final report.\n\n"
    "You have access to:\n"
    "- add_task(description, worker_binding_key): Spawn a researcher "
    "sub-agent. Use worker_binding_key='researchrubrics-researcher'.\n"
    "- abandon_task(node_id): Cancel a stalling sub-agent.\n"
    "- refine_task(node_id, new_description): Update a pending sub-agent's "
    "task description.\n"
    "- Resource discovery tools to observe researcher outputs\n\n"
    "Break the research question into sub-questions, spawn a researcher "
    "for each one using add_task, then observe their drafts via the "
    "resource discovery tools and provide your final synthesis."
)


class ResearchRubricsManagerWorker(ReActWorker):
    """Manager worker for researchrubrics benchmarks.

    Inventory: C2 task management + graph observability.  Spawns
    researchers via add_task; observes their drafts via list_child_resources
    and read tools.
    """

    type_slug: ClassVar[str] = "researchrubrics-manager"

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
            system_prompt=_MANAGER_SYSTEM_PROMPT,
            max_iterations=30,
        )

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        if context.node_id is None:
            raise RuntimeError("ResearchRubricsManagerWorker requires WorkerContext.node_id")
        if context.definition_id is None:
            raise RuntimeError(
                "ResearchRubricsManagerWorker requires WorkerContext.definition_id; "
                "it's the anchor TaskManagementToolkit uses to look up worker bindings "
                "when add_task() spawns children."
            )

        tm_toolkit = TaskManagementToolkit(
            run_id=context.run_id,
            definition_id=context.definition_id,
            parent_node_id=context.node_id,
        )
        tm_tools = tm_toolkit.get_tools()

        graph_toolkit = ResearchGraphToolkit(
            run_id=context.run_id,
            task_execution_id=context.execution_id,
        )
        graph_tools = graph_toolkit.build_tools()

        self.tools = [*tm_tools, *graph_tools]

        async for turn in super().execute(task, context=context):
            yield turn
