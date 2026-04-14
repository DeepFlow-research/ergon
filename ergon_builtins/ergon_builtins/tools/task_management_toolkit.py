"""Task management tools for dynamic delegation.

Produces pydantic-ai compatible tool callables that a manager agent
uses during its ReAct loop to spawn, abandon, and refine sub-tasks.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.runtime.services.task_management_dto import (
    AbandonTaskCommand,
    AddTaskCommand,
    RefineTaskCommand,
)
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)


class TaskManagementToolkit:
    """Produces pydantic-ai tool callables for delegation actions.

    Closures capture run_id, definition_id, and parent_node_id from
    WorkerContext + PreparedTaskExecution so the LLM never sees or
    guesses infrastructure IDs.
    """

    def __init__(
        self,
        *,
        run_id: UUID,
        definition_id: UUID,
        parent_node_id: UUID,
    ) -> None:
        self._run_id = run_id
        self._definition_id = definition_id
        self._parent_node_id = parent_node_id
        self._svc = TaskManagementService()

    def get_tools(self) -> list[Callable[..., Any]]:  # slopcop: ignore[no-typing-any]
        """Return the three delegation tools for Agent(tools=[...])."""
        return [
            self._make_add_task(),
            self._make_abandon_task(),
            self._make_refine_task(),
        ]

    def _make_add_task(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        svc = self._svc
        run_id = self._run_id
        definition_id = self._definition_id
        parent_node_id = self._parent_node_id

        async def add_task(
            description: str,
            worker_binding_key: str = "researcher",
        ) -> dict[str, object]:
            """Spawn a new sub-task that will be executed by a worker.

            Args:
                description: What the sub-task should accomplish.
                worker_binding_key: Binding key for worker resolution.
            """
            try:
                with get_session() as session:
                    result = svc.add_task(
                        session,
                        AddTaskCommand(
                            run_id=run_id,
                            definition_id=definition_id,
                            parent_node_id=parent_node_id,
                            description=description,
                            worker_binding_key=worker_binding_key,
                        ),
                    )
                await svc.dispatch_task_ready(
                    run_id=run_id,
                    definition_id=definition_id,
                    node_id=result.node_id,
                )
                return {
                    "success": True,
                    "node_id": str(result.node_id),
                    "task_key": result.task_key,
                }
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return add_task

    def _make_abandon_task(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        svc = self._svc
        run_id = self._run_id

        async def abandon_task(node_id: str) -> dict[str, object]:
            """Abandon a stalling or unnecessary sub-task.

            Args:
                node_id: The node_id of the sub-task to abandon.
            """
            try:
                with get_session() as session:
                    result = svc.abandon_task(
                        session,
                        AbandonTaskCommand(
                            run_id=run_id,
                            node_id=UUID(node_id),
                        ),
                    )
                return {
                    "success": True,
                    "node_id": str(result.node_id),
                    "previous_status": result.previous_status,
                }
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return abandon_task

    def _make_refine_task(self) -> Callable[..., Any]:  # slopcop: ignore[no-typing-any]
        svc = self._svc
        run_id = self._run_id

        async def refine_task(node_id: str, new_description: str) -> dict[str, object]:
            """Update the description of a pending sub-task before it executes.

            Args:
                node_id: The node_id of the pending sub-task to refine.
                new_description: The updated task description.
            """
            try:
                with get_session() as session:
                    result = svc.refine_task(
                        session,
                        RefineTaskCommand(
                            run_id=run_id,
                            node_id=UUID(node_id),
                            new_description=new_description,
                        ),
                    )
                return {
                    "success": True,
                    "node_id": str(result.node_id),
                    "old_description": result.old_description,
                    "new_description": result.new_description,
                }
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return {"success": False, "error": str(exc)}

        return refine_task
