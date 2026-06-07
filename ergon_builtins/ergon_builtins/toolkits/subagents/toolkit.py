"""Subtask lifecycle toolkit for manager agents.

Produces the eight manager-facing tool callables for ``Agent(tools=[...])``.
Replaces the old ``TaskManagementToolkit`` with expanded capabilities:
add_subtask, plan_subtasks, cancel_task, refine_task, restart_task,
list_subtasks, get_subtask, and sandboxed bash.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from ergon_core.api.task import Task
from ergon_core.api.worker import WorkerContext
from ergon_core.core.persistence.shared.types import (
    NodeId,
    TaskSlug,
)
from pydantic import BaseModel

from ergon_builtins.toolkits.subagents.sandbox_bash import make_sandbox_bash_tool
from ergon_builtins.toolkits.subagents.models import (
    AddSubtaskToolResponse,
    AddSubtaskToolSuccess,
    CancelTaskToolResponse,
    CancelTaskToolSuccess,
    GetSubtaskToolResponse,
    GetSubtaskToolSuccess,
    ListSubtasksToolResponse,
    ListSubtasksToolSuccess,
    PlanSubtasksToolResponse,
    RefineTaskToolResponse,
    RefineTaskToolSuccess,
    RestartTaskToolResponse,
    RestartTaskToolSuccess,
    ToolFailure,
)


class SubtaskLifecycleToolkit:
    """Produces the eight manager-facing tool callables for ``Agent(tools=[...])``.

    The toolkit is a closure factory, not a service: it captures
    ``sample_id`` and ``parent_task_id`` from ``WorkerContext`` so that
    creation tools (add_subtask, plan_subtasks, list_subtasks) are
    scoped to the manager's subtree by construction.

    Target-taking tools delegate containment to ``WorkerContext``. That
    facade verifies each supplied node id is this context's task id or a
    descendant before calling runtime task services, so the toolkit keeps
    only response-shaping and UUID parsing logic here.

    The toolkit only captures sample and task identity. Component
    bindings are read from the materialized sample graph at dispatch
    time, keeping the tool surface thin and avoiding stale runtime state.
    """

    def __init__(
        self,
        *,
        context: WorkerContext,
    ) -> None:
        if context is None:
            raise ValueError("SubtaskLifecycleToolkit requires context=WorkerContext.")
        self._context = context
        self._sandbox_id = context.sandbox_id

    def get_tools(self) -> list[Callable[..., Awaitable[BaseModel]]]:
        """Return the eight subtask lifecycle tools for Agent(tools=[...])."""
        return [
            self._make_add_subtask(),
            self._make_plan_subtasks(),
            self._make_cancel_task(),
            self._make_refine_task(),
            self._make_restart_task(),
            self._make_list_subtasks(),
            self._make_get_subtask(),
            make_sandbox_bash_tool(sandbox_id=self._sandbox_id),
        ]

    # -- management --------------------------------------------------------

    def _make_add_subtask(self) -> Callable[..., Awaitable[AddSubtaskToolResponse]]:
        context = self._context

        async def add_subtask(
            task: Task,
            depends_on: list[str] | None = None,
        ) -> AddSubtaskToolResponse:
            """Spawn one object-bound subtask under this worker context."""
            try:
                deps = tuple(UUID(s) for s in (depends_on or []))
                handle = await context.spawn_task(task, depends_on=deps)
                return AddSubtaskToolSuccess(
                    node_id=NodeId(handle.task_id),
                    task_slug=TaskSlug(task.task_slug),
                    status="pending",
                )
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return add_subtask

    def _make_plan_subtasks(self) -> Callable[..., Awaitable[PlanSubtasksToolResponse]]:
        async def plan_subtasks(_tasks: list[Task]) -> PlanSubtasksToolResponse:
            return ToolFailure(
                error=(
                    "plan_subtasks was removed from the worker-authoring toolkit; "
                    "call add_subtask with object-bound Task values."
                )
            )

        return plan_subtasks

    def _make_cancel_task(self) -> Callable[..., Awaitable[CancelTaskToolResponse]]:
        context = self._context

        async def cancel_task(node_id: str) -> CancelTaskToolResponse:
            """Cancel a contained subtask through WorkerContext."""
            try:
                await context.cancel_task(NodeId(UUID(node_id)))
                return CancelTaskToolSuccess(
                    node_id=NodeId(UUID(node_id)),
                    old_status="unknown",
                    cascaded_count=0,
                )
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return cancel_task

    def _make_refine_task(self) -> Callable[..., Awaitable[RefineTaskToolResponse]]:
        context = self._context

        async def refine_task(node_id: str, new_description: str) -> RefineTaskToolResponse:
            """Refine a contained subtask through WorkerContext."""
            try:
                await context.refine_task(NodeId(UUID(node_id)), description=new_description)
                return RefineTaskToolSuccess(
                    node_id=NodeId(UUID(node_id)),
                    old_description="",
                    new_description=new_description,
                )
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return refine_task

    def _make_restart_task(self) -> Callable[..., Awaitable[RestartTaskToolResponse]]:
        context = self._context

        async def restart_task(node_id: str) -> RestartTaskToolResponse:
            """Restart a contained subtask through WorkerContext."""
            try:
                await context.restart_task(NodeId(UUID(node_id)))
                return RestartTaskToolSuccess(
                    node_id=NodeId(UUID(node_id)),
                    old_status="unknown",
                    invalidated_node_ids=[],
                )
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return restart_task

    # -- inspection --------------------------------------------------------

    def _make_list_subtasks(self) -> Callable[..., Awaitable[ListSubtasksToolResponse]]:
        context = self._context

        async def list_subtasks() -> ListSubtasksToolResponse:
            """Return contained direct subtasks through WorkerContext."""
            try:
                infos = await context.subtasks()
                return ListSubtasksToolSuccess(subtasks=list(infos))
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return list_subtasks

    def _make_get_subtask(self) -> Callable[..., Awaitable[GetSubtaskToolResponse]]:
        context = self._context

        async def get_subtask(node_id: str) -> GetSubtaskToolResponse:
            """Return a contained subtask through WorkerContext."""
            try:
                info = await context.get_task(NodeId(UUID(node_id)))
                if isinstance(info, dict):
                    return GetSubtaskToolSuccess.model_validate(info)
                return GetSubtaskToolSuccess.model_validate(info.model_dump())
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return get_subtask


def build_subtask_lifecycle_tools(
    *,
    context: WorkerContext,
) -> list[Callable[..., Awaitable[BaseModel]]]:
    """Factory entry point for workers.

    Convenience wrapper so workers don't need to know about the toolkit class.
    """
    return SubtaskLifecycleToolkit(context=context).get_tools()
