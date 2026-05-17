"""Per-execution runtime state passed to Worker.execute()."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr

from ergon_core.api.benchmark.task import Task
from ergon_core.api.errors import ContainmentViolation
from ergon_core.api.worker.results import SpawnedTaskHandle


class WorkerContext(BaseModel):
    """Runtime context for a single worker execution.

    The facade owns the curated single-target API (``spawn_task``,
    ``cancel_task``, ``refine_task``, ``restart_task``, ``subtasks``,
    ``descendants``, ``get_task``). Containment is enforced: methods
    that target a ``task_id`` raise :class:`ContainmentViolation` if
    the target isn't this context's ``task_id`` or a descendant of it.
    """

    # NOTE: intentionally non-frozen. ``PrivateAttr`` fields are
    # injected via ``_for_job``; Pydantic ``frozen=True`` forbids
    # attribute setting at all, including ``object.__setattr__`` on
    # ``PrivateAttr``.
    model_config = {"arbitrary_types_allowed": True}

    run_id: UUID
    task_id: UUID | None = Field(
        default=None,
        description=(
            "RunGraphNode.task_id — canonical task identity. Optional "
            "in PR 9 during the column rename transition; PR 11 makes "
            "this required and removes node_id."
        ),
    )
    definition_id: UUID | None = Field(
        default=None,
        description=(
            "ExperimentDefinition.id — the experiment template that governs "
            "this run's worker bindings, evaluator bindings, and benchmark "
            "config. Used by delegation tools to resolve assigned_worker_slug "
            "to worker_type."
        ),
    )
    execution_id: UUID
    sandbox_id: str
    node_id: UUID | None = Field(
        default=None,
        description=(
            "RunGraphNode.id — bridge field during the schema "
            "transition. PR 11 removes this in favour of task_id."
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    # Injected services. Typed as ``Any`` (with a comment naming the
    # real class) to avoid an api → core → api import cycle:
    # ``TaskManagementService`` lives in
    # ``ergon_core.core.application.tasks.management`` which imports
    # ``from ergon_core.api.registry import registry``. Typing the
    # ``PrivateAttr`` with the real class would close that cycle.
    _task_mgmt: Any = PrivateAttr(
        default=None
    )  # TaskManagementService — slopcop: ignore[no-typing-any]
    _task_inspect: Any = PrivateAttr(
        default=None
    )  # TaskInspectionService — slopcop: ignore[no-typing-any]
    _resource_repo: Any = PrivateAttr(
        default=None
    )  # RunResourceRepository — slopcop: ignore[no-typing-any]

    @classmethod
    def _for_job(
        cls,
        *,
        run_id: UUID,
        task_id: UUID | None,
        execution_id: UUID,
        definition_id: UUID | None,
        sandbox_id: str,
        node_id: UUID | None,
        task_mgmt: Any,  # TaskManagementService — slopcop: ignore[no-typing-any]
        task_inspect: Any,  # TaskInspectionService — slopcop: ignore[no-typing-any]
        resource_repo: Any,  # RunResourceRepository — slopcop: ignore[no-typing-any]
    ) -> "WorkerContext":
        """Construct a ``WorkerContext`` with services injected.

        The single canonical construction site used by ``worker_execute``.
        Tests that need to exercise the facade should call this; tests
        that only need a plain context (no facade methods) can keep
        constructing ``WorkerContext(...)`` directly — the
        ``PrivateAttr`` services then stay ``None``.
        """

        instance = cls(
            run_id=run_id,
            task_id=task_id,
            execution_id=execution_id,
            definition_id=definition_id,
            sandbox_id=sandbox_id,
            node_id=node_id,
        )
        object.__setattr__(instance, "_task_mgmt", task_mgmt)
        object.__setattr__(instance, "_task_inspect", task_inspect)
        object.__setattr__(instance, "_resource_repo", resource_repo)
        return instance

    # ── facade methods ─────────────────────────────────────────────────

    async def spawn_task(
        self,
        task: Task,
        *,
        depends_on: tuple[UUID, ...] = (),
    ) -> SpawnedTaskHandle:
        """Spawn a child task under this context's task_id."""

        return await self._task_mgmt.add_subtask(
            run_id=self.run_id,
            parent_task_id=self.task_id,
            task=task,
            depends_on=depends_on,
        )

    async def cancel_task(self, task_id: UUID, *, reason: str = "") -> None:
        """Cancel a descendant task. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        await self._task_mgmt.cancel_task(
            run_id=self.run_id,
            task_id=task_id,
            reason=reason,
        )

    async def refine_task(self, task_id: UUID, *, description: str) -> None:
        """Refine a descendant task's description. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        await self._task_mgmt.refine_task(
            run_id=self.run_id,
            task_id=task_id,
            description=description,
        )

    async def restart_task(self, task_id: UUID) -> SpawnedTaskHandle:
        """Restart a descendant task. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        return await self._task_mgmt.restart_task(
            run_id=self.run_id,
            task_id=task_id,
        )

    async def subtasks(self) -> tuple[Task, ...]:
        """Return the direct children of this context's task_id."""

        return await self._task_inspect.children(
            run_id=self.run_id,
            parent_task_id=self.task_id,
        )

    async def descendants(self) -> tuple[Task, ...]:
        """Return the transitive descendants of this context's task_id."""

        return await self._task_inspect.descendants(
            run_id=self.run_id,
            root_task_id=self.task_id,
        )

    async def get_task(self, task_id: UUID) -> Task:
        """Fetch a descendant task by id. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        return await self._task_inspect.get(
            run_id=self.run_id,
            task_id=task_id,
        )

    async def _assert_descendant(self, task_id: UUID) -> None:
        """Raise ``ContainmentViolation`` if ``task_id`` is not self.task_id or a descendant."""

        if task_id == self.task_id:
            return
        descendant_ids = await self._task_inspect.descendant_ids(
            run_id=self.run_id,
            root_task_id=self.task_id,
        )
        if task_id not in descendant_ids:
            raise ContainmentViolation(
                parent_task_id=self.task_id,
                target_task_id=task_id,
            )
