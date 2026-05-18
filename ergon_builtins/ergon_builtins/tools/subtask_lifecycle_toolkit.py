"""Subtask lifecycle toolkit for manager agents.

Produces the eight manager-facing tool callables for ``Agent(tools=[...])``.
Replaces the old ``TaskManagementToolkit`` with expanded capabilities:
add_subtask, plan_subtasks, cancel_task, refine_task, restart_task,
list_subtasks, get_subtask, and sandboxed bash.
"""

from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import UUID

from ergon_core.api.benchmark import Task
from ergon_core.api.worker import WorkerContext
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import (
    AssignedWorkerSlug,
    NodeId,
    RunId,
    TaskSlug,
)
from ergon_core.core.application.tasks.models import SubtaskInfo
from ergon_core.core.application.tasks.inspection import TaskInspectionService
from ergon_core.core.application.tasks.models import (
    AddSubtaskCommand,
    CancelTaskCommand,
    PlanSubtasksCommand,
    RefineTaskCommand,
    RestartTaskCommand,
    SubtaskSpec,
)
from ergon_core.core.application.tasks.management import TaskManagementService
from pydantic import BaseModel

from ergon_builtins.tools.bash_sandbox_tool import make_sandbox_bash_tool


class ToolFailure(BaseModel):
    kind: Literal["failure"] = "failure"
    error: str

    model_config = {"frozen": True}


class AddSubtaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    task_slug: TaskSlug
    status: str

    model_config = {"frozen": True}


type AddSubtaskToolResponse = AddSubtaskToolSuccess | ToolFailure


class PlanSubtasksToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    nodes: dict[TaskSlug, NodeId]
    roots: list[TaskSlug]

    model_config = {"frozen": True}


type PlanSubtasksToolResponse = PlanSubtasksToolSuccess | ToolFailure


class CancelTaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    old_status: str
    cascaded_count: int

    model_config = {"frozen": True}


type CancelTaskToolResponse = CancelTaskToolSuccess | ToolFailure


class RefineTaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    old_description: str
    new_description: str

    model_config = {"frozen": True}


type RefineTaskToolResponse = RefineTaskToolSuccess | ToolFailure


class RestartTaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    old_status: str
    invalidated_node_ids: list[NodeId]

    model_config = {"frozen": True}


type RestartTaskToolResponse = RestartTaskToolSuccess | ToolFailure


class ListSubtasksToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    subtasks: list[SubtaskInfo]

    model_config = {"frozen": True}


type ListSubtasksToolResponse = ListSubtasksToolSuccess | ToolFailure


class GetSubtaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    task_slug: str
    description: str
    status: str
    depends_on: list[NodeId]
    output: str | None
    error: str | None

    model_config = {"frozen": True}


type GetSubtaskToolResponse = GetSubtaskToolSuccess | ToolFailure


class SubtaskLifecycleToolkit:
    """Produces the eight manager-facing tool callables for ``Agent(tools=[...])``.

    The toolkit is a closure factory, not a service: it captures
    ``run_id`` and ``parent_node_id`` from ``WorkerContext`` so that
    creation tools (add_subtask, plan_subtasks, list_subtasks) are
    scoped to the manager's subtree by construction.

    Note: cancel_task, refine_task, and get_subtask accept a
    ``node_id`` from the LLM and do not yet verify containment
    (i.e. that the target is a descendant of ``parent_node_id``).
    The service layer checks status guards but not subtree membership.
    TODO: add descendant-of check for full containment enforcement.

    ``definition_id`` is NOT captured here --- the service resolves it
    from ``run_id`` at dispatch time, keeping the tool surface
    thin and eliminating a class of stale-id bugs when definitions are
    reloaded mid-run.
    """

    def __init__(
        self,
        *,
        run_id: UUID | None = None,
        parent_node_id: UUID | None = None,
        sandbox_id: str | None = None,
        context: WorkerContext | None = None,
        task_management_service: TaskManagementService | None = None,
        task_inspection_service: TaskInspectionService | None = None,
    ) -> None:
        if context is None and (run_id is None or parent_node_id is None or sandbox_id is None):
            raise ValueError(
                "SubtaskLifecycleToolkit requires either context=WorkerContext or "
                "explicit run_id, parent_node_id, and sandbox_id for the admin path."
            )
        self._context = context
        self._run_id = None if run_id is None else RunId(run_id)
        self._parent_node_id = None if parent_node_id is None else NodeId(parent_node_id)
        self._sandbox_id = sandbox_id if sandbox_id is not None else context.sandbox_id
        self._mgmt = (
            None if context is not None else task_management_service or TaskManagementService()
        )
        self._inspect = (
            None if context is not None else task_inspection_service or TaskInspectionService()
        )

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
        if self._context is not None:
            context = self._context

            async def add_subtask(
                task: Task, depends_on: list[str] | None = None
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

        mgmt, run_id, pid = self._mgmt, self._run_id, self._parent_node_id
        if run_id is None or pid is None:
            raise RuntimeError("admin add_subtask requires run_id and parent_node_id")

        async def add_subtask(
            task_slug: str,
            description: str,
            assigned_worker_slug: str,
            depends_on: list[str] | None = None,
        ) -> AddSubtaskToolResponse:
            """Spawn one subtask under this manager.

            The ``task_slug`` is a short kebab-case identifier for this
            subtask. It is persisted verbatim on the graph node and used
            by observers (dashboard, criteria, tests) to identify this
            node semantically. Pick a stable, legible slug — it is not
            auto-generated.

            ``assigned_worker_slug`` is the slug of the worker type to handle this
            subtask (e.g. 'researchrubrics-researcher'). Required.

            ``depends_on`` still refers to sibling ``node_id`` strings
            (real UUIDs from earlier ``add_subtask`` calls), not slugs.
            """
            try:
                deps = [NodeId(UUID(s)) for s in (depends_on or [])]
                with get_session() as session:
                    result = await mgmt.add_subtask(
                        session,
                        AddSubtaskCommand(
                            run_id=run_id,
                            parent_node_id=pid,
                            task_slug=TaskSlug(task_slug),
                            description=description,
                            assigned_worker_slug=AssignedWorkerSlug(assigned_worker_slug),
                            depends_on=deps,
                        ),
                    )
                return AddSubtaskToolSuccess.model_validate(result.model_dump())
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return add_subtask

    def _make_plan_subtasks(self) -> Callable[..., Awaitable[PlanSubtasksToolResponse]]:
        mgmt, run_id, pid = self._mgmt, self._run_id, self._parent_node_id
        if run_id is None or pid is None:

            async def plan_subtasks(_subtasks: list[SubtaskSpec]) -> PlanSubtasksToolResponse:
                return ToolFailure(
                    error=(
                        "plan_subtasks is not available through worker-context "
                        "containment; spawn object-bound tasks one at a time."
                    )
                )

            return plan_subtasks

        async def plan_subtasks(subtasks: list[SubtaskSpec]) -> PlanSubtasksToolResponse:
            """Atomically create a sub-DAG. Each entry has ``task_slug``
            (kebab-case identifier, persisted verbatim on the graph node),
            ``description``, required ``assigned_worker_slug``, and
            optional ``depends_on`` — a list of sibling ``task_slug``s
            within this same call. Cycles, duplicate slugs, and unknown
            slugs are rejected."""
            try:
                with get_session() as session:
                    result = await mgmt.plan_subtasks(
                        session,
                        PlanSubtasksCommand(
                            run_id=run_id,
                            parent_node_id=pid,
                            subtasks=subtasks,
                        ),
                    )
                return PlanSubtasksToolSuccess.model_validate(result.model_dump())
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return plan_subtasks

    def _make_cancel_task(self) -> Callable[..., Awaitable[CancelTaskToolResponse]]:
        if self._context is not None:
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

        mgmt, run_id = self._mgmt, self._run_id
        if run_id is None:
            raise RuntimeError("admin cancel_task requires run_id")

        async def cancel_task(node_id: str) -> CancelTaskToolResponse:
            """Cancel a subtask. Any descendants are cancelled via engine cascade."""
            try:
                with get_session() as session:
                    result = await mgmt.cancel_task(
                        session,
                        CancelTaskCommand(run_id=run_id, node_id=NodeId(UUID(node_id))),
                    )
                return CancelTaskToolSuccess.model_validate(result.model_dump())
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return cancel_task

    def _make_refine_task(self) -> Callable[..., Awaitable[RefineTaskToolResponse]]:
        if self._context is not None:
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

        mgmt, run_id = self._mgmt, self._run_id
        if run_id is None:
            raise RuntimeError("admin refine_task requires run_id")

        async def refine_task(node_id: str, new_description: str) -> RefineTaskToolResponse:
            """Refine a subtask's description. Allowed on any status except RUNNING.

            Pairs with ``restart_task`` for the edit-then-rerun flow: call
            ``refine_task`` first to update the description, then
            ``restart_task`` to put the node back in the scheduling queue.
            """
            try:
                with get_session() as session:
                    result = await mgmt.refine_task(
                        session,
                        RefineTaskCommand(
                            run_id=run_id,
                            node_id=NodeId(UUID(node_id)),
                            new_description=new_description,
                        ),
                    )
                return RefineTaskToolSuccess.model_validate(result.model_dump())
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return refine_task

    def _make_restart_task(self) -> Callable[..., Awaitable[RestartTaskToolResponse]]:
        if self._context is not None:
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

        mgmt, run_id = self._mgmt, self._run_id
        if run_id is None:
            raise RuntimeError("admin restart_task requires run_id")

        async def restart_task(node_id: str) -> RestartTaskToolResponse:
            """Reset a terminal subtask back to PENDING and re-dispatch.

            Only nodes in terminal status (COMPLETED / FAILED / CANCELLED)
            may be restarted. Downstream targets that were running against
            stale input are invalidated (cancelled and re-queued) so the
            subgraph is consistent when this node re-runs.
            """
            try:
                with get_session() as session:
                    result = await mgmt.restart_task(
                        session,
                        RestartTaskCommand(
                            run_id=run_id,
                            node_id=NodeId(UUID(node_id)),
                        ),
                    )
                return RestartTaskToolSuccess.model_validate(result.model_dump())
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return restart_task

    # -- inspection --------------------------------------------------------

    def _make_list_subtasks(self) -> Callable[..., Awaitable[ListSubtasksToolResponse]]:
        if self._context is not None:
            context = self._context

            async def list_subtasks() -> ListSubtasksToolResponse:
                """Return contained direct subtasks through WorkerContext."""
                try:
                    infos = await context.subtasks()
                    return ListSubtasksToolSuccess(subtasks=list(infos))
                except Exception as exc:  # slopcop: ignore[no-broad-except]
                    return ToolFailure(error=str(exc))

            return list_subtasks

        inspect, run_id, pid = self._inspect, self._run_id, self._parent_node_id
        if run_id is None or pid is None:
            raise RuntimeError("admin list_subtasks requires run_id and parent_node_id")

        async def list_subtasks() -> ListSubtasksToolResponse:
            """Return the current status and output-excerpt of every direct subtask."""
            try:
                with get_session() as session:
                    infos = inspect.list_subtasks(session, run_id=run_id, parent_node_id=pid)
                return ListSubtasksToolSuccess(subtasks=infos)
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return list_subtasks

    def _make_get_subtask(self) -> Callable[..., Awaitable[GetSubtaskToolResponse]]:
        if self._context is not None:
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

        inspect, run_id = self._inspect, self._run_id
        if run_id is None:
            raise RuntimeError("admin get_subtask requires run_id")

        async def get_subtask(node_id: str) -> GetSubtaskToolResponse:
            """Return the full SubtaskInfo for one node_id."""
            try:
                with get_session() as session:
                    info = inspect.get_subtask(
                        session, run_id=run_id, node_id=NodeId(UUID(node_id))
                    )
                return GetSubtaskToolSuccess.model_validate(info.model_dump())
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return ToolFailure(error=str(exc))

        return get_subtask


def build_subtask_lifecycle_tools(
    *,
    run_id: UUID,
    parent_node_id: UUID,
    sandbox_id: str,
) -> list[Callable[..., Awaitable[BaseModel]]]:
    """Factory entry point for workers.

    Convenience wrapper so workers don't need to know about the toolkit class.
    """
    return SubtaskLifecycleToolkit(
        run_id=run_id,
        parent_node_id=parent_node_id,
        sandbox_id=sandbox_id,
    ).get_tools()
