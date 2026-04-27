"""Recursive smoke worker used by happy-path E2E runs.

This worker is assigned to the top-level ``l_2`` node.  It plans two
nested leaf subtasks under itself, waits for them to complete, then sends
the same completion-thread message shape as a normal leaf.  The top-level
``l_3`` dependency therefore waits on a non-leaf dynamic task.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import UUID

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.api.results import WorkerOutput
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import TERMINAL_STATUSES
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, NodeId, RunId, TaskSlug
from ergon_core.core.runtime.services.communication_schemas import CreateMessageRequest
from ergon_core.core.runtime.services.communication_service import communication_service
from ergon_core.core.runtime.services.task_inspection_service import TaskInspectionService
from ergon_core.core.runtime.services.task_management_dto import PlanSubtasksCommand, SubtaskSpec
from ergon_core.core.runtime.services.task_management_service import TaskManagementService

NESTED_LINE_SLUGS: tuple[str, ...] = ("l_2_a", "l_2_b")
NESTED_SUBTASK_GRAPH: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("l_2_a", (), "Nested line node 2a"),
    ("l_2_b", ("l_2_a",), "Nested line node 2b"),
)


class RecursiveSmokeWorkerBase(Worker):
    """Plan and wait for a two-node nested line under ``l_2``."""

    leaf_slug: ClassVar[str]
    RECURSIVE_TURN_COUNT: ClassVar[int] = 3

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_child_statuses: dict[str, str] = {}

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        if context.node_id is None:
            raise ValueError(f"{type(self).__name__} requires context.node_id")

        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"{type(self).__name__}: planning nested "
                        f"{' -> '.join(NESTED_LINE_SLUGS)} via leaf={self.leaf_slug}"
                    ),
                ),
            ],
        )

        specs = [
            SubtaskSpec(
                task_slug=TaskSlug(slug),
                description=desc,
                assigned_worker_slug=AssignedWorkerSlug(self.leaf_slug),
                depends_on=[TaskSlug(dep) for dep in deps],
            )
            for slug, deps, desc in NESTED_SUBTASK_GRAPH
        ]
        with get_session() as session:
            result = await TaskManagementService().plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=RunId(context.run_id),
                    parent_node_id=NodeId(context.node_id),
                    subtasks=specs,
                ),
            )

        summary = "\n".join(
            f"{slug}: planned (node_id={result.nodes[TaskSlug(slug)]})"
            for slug, _deps, _desc in NESTED_SUBTASK_GRAPH
        )
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=f"{type(self).__name__}: nested subtasks planned:\n{summary}",
                ),
            ],
        )

        inspection = TaskInspectionService()
        while True:
            with get_session() as session:
                children = inspection.list_subtasks(
                    session,
                    run_id=context.run_id,
                    parent_node_id=context.node_id,
                )
            if children and all(c.status in TERMINAL_STATUSES for c in children):
                self._last_child_statuses = {c.task_slug: c.status for c in children}
                break
            await asyncio.sleep(2)

        await self._send_recursive_completion_message(context)
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"{type(self).__name__}: nested children terminal "
                        f"{self._last_child_statuses}"
                    ),
                ),
            ],
        )

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        non_completed = {
            slug: status
            for slug, status in self._last_child_statuses.items()
            if status != "completed"
        }
        if non_completed:
            return WorkerOutput(
                output=f"nested children did not all complete: {non_completed}",
                success=False,
                metadata={"child_statuses": self._last_child_statuses},
            )
        return WorkerOutput(
            output="nested smoke recursion completed",
            success=True,
            metadata={"child_statuses": self._last_child_statuses},
        )

    async def _send_recursive_completion_message(self, context: WorkerContext) -> None:
        task_slug = self._lookup_task_slug(context.node_id)
        await communication_service.save_message(
            CreateMessageRequest(
                run_id=context.run_id,
                task_execution_id=context.execution_id,
                from_agent_id=f"leaf-{task_slug}",
                to_agent_id="parent",
                thread_topic="smoke-completion",
                content=(
                    f"{task_slug}: recursive done nested={sorted(self._last_child_statuses)}"
                ),
            ),
        )

    @staticmethod
    def _lookup_task_slug(node_id: UUID | None) -> str:
        if node_id is None:
            return "unknown"
        with get_session() as session:
            node = session.get(RunGraphNode, node_id)
        return node.task_slug if node is not None else f"node-{node_id.hex[:8]}"


class RecursiveSmokeWorkerMixin:
    """Route top-level ``l_2`` to an env-specific recursive worker."""

    RECURSIVE_SLUGS: ClassVar[frozenset[str]] = frozenset({"l_2"})
    RECURSIVE_WORKER_SLUG: ClassVar[str]
    leaf_slug: ClassVar[str]

    def _spec_for(self, slug, deps, desc):
        worker_slug = self.RECURSIVE_WORKER_SLUG if slug in self.RECURSIVE_SLUGS else self.leaf_slug
        return SubtaskSpec(
            task_slug=TaskSlug(slug),
            description=desc,
            assigned_worker_slug=AssignedWorkerSlug(worker_slug),
            depends_on=[TaskSlug(d) for d in deps],
        )


__all__ = [
    "NESTED_LINE_SLUGS",
    "NESTED_SUBTASK_GRAPH",
    "RecursiveSmokeWorkerBase",
    "RecursiveSmokeWorkerMixin",
]
