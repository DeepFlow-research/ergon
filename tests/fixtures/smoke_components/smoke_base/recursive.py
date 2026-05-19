"""Recursive smoke worker used by happy-path E2E runs.

This worker is assigned to the top-level ``l_2`` node.  It plans two
nested leaf subtasks under itself, waits for them to complete, then sends
the same completion-thread message shape as a normal leaf.  The top-level
``l_3`` dependency therefore waits on a non-leaf dynamic task.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import UUID

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.shared.context_parts import AssistantTextPart, ContextPartChunk
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from ergon_core.core.application.communication.models import CreateMessageRequest
from ergon_core.core.application.communication.service import communication_service
from ergon_core.core.application.tasks.models import SubtaskSpec
from tests.fixtures.smoke_components.smoke_base.dynamic_tasks import smoke_task_from_spec
from sqlmodel import select

NESTED_LINE_SLUGS: tuple[str, ...] = ("l_2_a", "l_2_b")
NESTED_SUBTASK_GRAPH: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("l_2_a", (), "Nested line node 2a"),
    ("l_2_b", ("l_2_a",), "Nested line node 2b"),
)


class RecursiveSmokeWorkerBase(Worker):
    """Plan and wait for a two-node nested line under ``l_2``."""

    leaf_slug: ClassVar[str]
    RECURSIVE_TURN_COUNT: ClassVar[int] = 3

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        if context.task_id is None:
            raise ValueError(f"{type(self).__name__} requires context.task_id")

        yield ContextPartChunk(
            part=AssistantTextPart(
                content=(
                    f"{type(self).__name__}: planning nested "
                    f"{' -> '.join(NESTED_LINE_SLUGS)} via leaf={self.leaf_slug}"
                ),
            ),
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
        planned: dict[TaskSlug, UUID] = {}
        for spec in specs:
            child_task = smoke_task_from_spec(
                parent_task=task,
                spec=spec,
                model=self.model,
            )
            dependency_task_ids = tuple(planned[dep] for dep in spec.depends_on)
            handle = await context.spawn_task(child_task, depends_on=dependency_task_ids)
            planned[spec.task_slug] = handle.task_id

        summary = "\n".join(
            f"{slug}: planned (task_id={planned[TaskSlug(slug)]})"
            for slug, _deps, _desc in NESTED_SUBTASK_GRAPH
        )
        yield ContextPartChunk(
            part=AssistantTextPart(
                content=f"{type(self).__name__}: nested subtasks planned:\n{summary}",
            ),
        )

        planned_children = sorted(str(slug) for slug in planned)
        await self._send_recursive_completion_message(context, planned_children)
        yield ContextPartChunk(
            part=AssistantTextPart(
                content=f"{type(self).__name__}: nested children planned {planned_children}",
            ),
        )

        yield WorkerOutput(
            output="nested smoke recursion planned",
            success=True,
            metadata={
                "planned_children": planned_children,
                "child_wait_mode": "criterion",
            },
        )

    async def _send_recursive_completion_message(
        self,
        context: WorkerContext,
        planned_children: list[str],
    ) -> None:
        task_slug = self._lookup_task_slug(context.task_id)
        await communication_service.save_message(
            CreateMessageRequest(
                run_id=context.run_id,
                task_execution_id=context.execution_id,
                from_agent_id=f"leaf-{task_slug}",
                to_agent_id="parent",
                thread_topic="smoke-completion",
                content=(f"{task_slug}: recursive planned nested={planned_children}"),
            ),
        )

    @staticmethod
    def _lookup_task_slug(task_id: UUID | None) -> str:
        if task_id is None:
            return "unknown"
        with get_session() as session:
            node = session.exec(select(RunGraphNode).where(RunGraphNode.task_id == task_id)).first()
        return node.task_slug if node is not None else f"node-{task_id.hex[:8]}"


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
