"""Subtask lifecycle toolkit for manager agents.

Produces the eight manager-facing tool callables for ``Agent(tools=[...])``.
Replaces the old ``TaskManagementToolkit`` with expanded capabilities:
add_subtask, plan_subtasks, cancel_task, refine_task, restart_task,
list_subtasks, get_subtask, and sandboxed bash.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import NodeId, RunId
from ergon_core.core.runtime.services.task_management_dto import (
    AddSubtaskCommand,
    CancelTaskCommand,
    PlanSubtasksCommand,
    RefineTaskCommand,
    RestartTaskCommand,
    SubtaskSpec,
)
from ergon_core.core.runtime.services.task_management_service import TaskManagementService
from ergon_core.core.runtime.services.task_inspection_service import TaskInspectionService

from ergon_builtins.tools.bash_sandbox_tool import make_sandbox_bash_tool


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
        run_id: UUID,
        parent_node_id: UUID,
        sandbox_id: str,
    ) -> None:
        self._run_id = RunId(run_id)
        self._parent_node_id = NodeId(parent_node_id)
        self._sandbox_id = sandbox_id
        self._mgmt = TaskManagementService()
        self._inspect = TaskInspectionService()

    def get_tools(self) -> list[Callable[..., Any]]:  # slopcop: ignore[no-typing-any]
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

    def _make_add_subtask(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        mgmt, run_id, pid = self._mgmt, self._run_id, self._parent_node_id

        async def add_subtask(
            description: str,
            worker_binding_key: str = "researcher",
            depends_on: list[str] | None = None,
        ) -> dict[str, object]:
            """Spawn one subtask under this manager. Optionally blocked by sibling node_ids."""
            try:
                deps = [NodeId(UUID(s)) for s in (depends_on or [])]
                with get_session() as session:
                    result = mgmt.add_subtask(
                        session,
                        AddSubtaskCommand(
                            run_id=run_id,
                            parent_node_id=pid,
                            description=description,
                            worker_binding_key=worker_binding_key,
                            depends_on=deps,
                        ),
                    )
                return {"success": True, **result.model_dump(mode="json")}
            except Exception as exc:  # noqa: BLE001  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return add_subtask

    def _make_plan_subtasks(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        mgmt, run_id, pid = self._mgmt, self._run_id, self._parent_node_id

        async def plan_subtasks(subtasks: list[dict]) -> dict[str, object]:
            """Atomically create a sub-DAG. Each entry has local_key, description,
            optional worker_binding_key, optional depends_on (list[str] of other
            local_keys). Cycles / duplicate / unknown keys are rejected."""
            try:
                specs = [SubtaskSpec.model_validate(s) for s in subtasks]
                with get_session() as session:
                    result = mgmt.plan_subtasks(
                        session,
                        PlanSubtasksCommand(
                            run_id=run_id,
                            parent_node_id=pid,
                            subtasks=specs,
                        ),
                    )
                return {"success": True, **result.model_dump(mode="json")}
            except Exception as exc:  # noqa: BLE001  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return plan_subtasks

    def _make_cancel_task(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        mgmt, run_id = self._mgmt, self._run_id

        async def cancel_task(node_id: str) -> dict[str, object]:
            """Cancel a subtask. Any descendants are cancelled via engine cascade."""
            try:
                with get_session() as session:
                    result = mgmt.cancel_task(
                        session,
                        CancelTaskCommand(run_id=run_id, node_id=NodeId(UUID(node_id))),
                    )
                return {"success": True, **result.model_dump(mode="json")}
            except Exception as exc:  # noqa: BLE001  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return cancel_task

    def _make_refine_task(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        mgmt, run_id = self._mgmt, self._run_id

        async def refine_task(node_id: str, new_description: str) -> dict[str, object]:
            """Refine a subtask's description. Allowed on any status except RUNNING.

            Pairs with ``restart_task`` for the edit-then-rerun flow: call
            ``refine_task`` first to update the description, then
            ``restart_task`` to put the node back in the scheduling queue.
            """
            try:
                with get_session() as session:
                    result = mgmt.refine_task(
                        session,
                        RefineTaskCommand(
                            run_id=run_id,
                            node_id=NodeId(UUID(node_id)),
                            new_description=new_description,
                        ),
                    )
                return {"success": True, **result.model_dump(mode="json")}
            except Exception as exc:  # noqa: BLE001  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return refine_task

    def _make_restart_task(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        mgmt, run_id = self._mgmt, self._run_id

        async def restart_task(node_id: str) -> dict[str, object]:
            """Reset a terminal subtask back to PENDING and re-dispatch.

            Only nodes in terminal status (COMPLETED / FAILED / CANCELLED)
            may be restarted. Downstream targets that were running against
            stale input are invalidated (cancelled and re-queued) so the
            subgraph is consistent when this node re-runs.
            """
            try:
                with get_session() as session:
                    result = mgmt.restart_task(
                        session,
                        RestartTaskCommand(
                            run_id=run_id,
                            node_id=NodeId(UUID(node_id)),
                        ),
                    )
                return {"success": True, **result.model_dump(mode="json")}
            except Exception as exc:  # noqa: BLE001  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return restart_task

    # -- inspection --------------------------------------------------------

    def _make_list_subtasks(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        inspect, run_id, pid = self._inspect, self._run_id, self._parent_node_id

        async def list_subtasks() -> dict[str, object]:
            """Return the current status and output-excerpt of every direct subtask."""
            try:
                with get_session() as session:
                    infos = inspect.list_subtasks(session, run_id=run_id, parent_node_id=pid)
                return {
                    "success": True,
                    "subtasks": [i.model_dump(mode="json") for i in infos],
                }
            except Exception as exc:  # noqa: BLE001  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return list_subtasks

    def _make_get_subtask(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        inspect, run_id = self._inspect, self._run_id

        async def get_subtask(node_id: str) -> dict[str, object]:
            """Return the full SubtaskInfo for one node_id."""
            try:
                with get_session() as session:
                    info = inspect.get_subtask(
                        session, run_id=run_id, node_id=NodeId(UUID(node_id))
                    )
                return {"success": True, **info.model_dump(mode="json")}
            except Exception as exc:  # noqa: BLE001  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return get_subtask


def build_subtask_lifecycle_tools(
    *,
    run_id: UUID,
    parent_node_id: UUID,
    sandbox_id: str,
) -> list[Callable[..., Any]]:  # slopcop: ignore[no-typing-any]
    """Factory entry point for workers.

    Convenience wrapper so workers don't need to know about the toolkit class.
    """
    return SubtaskLifecycleToolkit(
        run_id=run_id,
        parent_node_id=parent_node_id,
        sandbox_id=sandbox_id,
    ).get_tools()
