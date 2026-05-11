"""Per-execution runtime state passed to Worker.execute()."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr
from ergon_core.api.errors import ContainmentViolation
from ergon_core.core.application.resources.models import RunResourceView
from ergon_core.core.shared.json_types import JsonObject

if TYPE_CHECKING:
    from ergon_core.api.benchmark.task import Task
    from ergon_core.core.application.tasks.models import SubtaskInfo


class SpawnedTaskHandle(BaseModel):
    """Small fire-and-forget handle returned after spawning a child task."""

    model_config = {"frozen": True}

    task_id: UUID
    task_slug: str
    status: str


class WorkerContext(BaseModel):
    """Runtime context for a single worker execution."""

    model_config = {"frozen": True}

    run_id: UUID
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
    sandbox_id: str | None = None
    task_id: UUID
    node_id: UUID | None = Field(
        default=None,
        description="RunGraphNode.id — this worker's graph node identity.",
    )
    metadata: JsonObject = Field(default_factory=dict)

    _task_mgmt: Any = PrivateAttr(default=None)  # slopcop: ignore[no-typing-any]
    _task_inspect: Any = PrivateAttr(default=None)  # slopcop: ignore[no-typing-any]
    _resource_repo: Any = PrivateAttr(default=None)  # slopcop: ignore[no-typing-any]
    _session_factory: Callable[[], AbstractContextManager[Any]] | None = PrivateAttr(default=None)

    @classmethod
    def _for_job(
        cls,
        *,
        run_id: UUID,
        definition_id: UUID,
        execution_id: UUID,
        task_id: UUID,
        task_mgmt: Any,  # slopcop: ignore[no-typing-any]
        task_inspect: Any,  # slopcop: ignore[no-typing-any]
        resource_repo: Any,  # slopcop: ignore[no-typing-any]
        session_factory: Callable[[], AbstractContextManager[Any]],
        metadata: JsonObject | None = None,
    ) -> "WorkerContext":
        """Framework-only constructor that wires runtime services as private state."""
        instance = cls(
            run_id=run_id,
            definition_id=definition_id,
            execution_id=execution_id,
            task_id=task_id,
            metadata=dict(metadata or {}),
        )
        object.__setattr__(instance, "_task_mgmt", task_mgmt)
        object.__setattr__(instance, "_task_inspect", task_inspect)
        object.__setattr__(instance, "_resource_repo", resource_repo)
        object.__setattr__(instance, "_session_factory", session_factory)
        return instance

    async def spawn_task(
        self,
        task: Task,
        *,
        depends_on: tuple[UUID, ...] = (),
    ) -> SpawnedTaskHandle:
        """Spawn one child task under this worker's current task."""
        with self._session_factory_required()() as session:
            result = await self._task_mgmt_required().spawn_task(
                session,
                run_id=self.run_id,
                parent_task_id=self.task_id,
                task=task,
                depends_on=list(depends_on),
            )
        return SpawnedTaskHandle(
            task_id=result.task_id,
            task_slug=result.task_slug,
            status=result.status,
        )

    async def cancel_task(self, task_id: UUID) -> None:
        """Cancel one descendant task."""
        self._assert_descendant(task_id)
        with self._session_factory_required()() as session:
            await self._task_mgmt_required().cancel_task_by_id(
                session,
                run_id=self.run_id,
                task_id=task_id,
            )

    async def refine_task(self, task_id: UUID, *, description: str) -> None:
        """Update the description of one descendant task."""
        self._assert_descendant(task_id)
        with self._session_factory_required()() as session:
            await self._task_mgmt_required().refine_task_by_id(
                session,
                run_id=self.run_id,
                task_id=task_id,
                description=description,
            )

    async def restart_task(self, task_id: UUID) -> None:
        """Reset one terminal descendant task back to pending."""
        self._assert_descendant(task_id)
        with self._session_factory_required()() as session:
            await self._task_mgmt_required().restart_task_by_id(
                session,
                run_id=self.run_id,
                task_id=task_id,
            )

    def subtasks(self) -> Iterable[SubtaskInfo]:
        """Direct children of this worker's task."""
        with self._session_factory_required()() as session:
            return self._task_inspect_required().list_subtasks(
                session,
                run_id=self.run_id,
                parent_task_id=self.task_id,
            )

    def descendants(self, *, max_depth: int = 3) -> Iterable[SubtaskInfo]:
        """BFS over this worker's task subtree."""
        with self._session_factory_required()() as session:
            return self._task_inspect_required().descendants(
                session,
                run_id=self.run_id,
                parent_task_id=self.task_id,
                max_depth=max_depth,
            )

    def get_task(self, task_id: UUID) -> SubtaskInfo:
        """Fetch this task or one descendant task."""
        if task_id != self.task_id:
            self._assert_descendant(task_id)
        with self._session_factory_required()() as session:
            return self._task_inspect_required().get_task(
                session,
                run_id=self.run_id,
                task_id=task_id,
            )

    def resources(
        self,
        *,
        scope: Literal["own", "children", "descendants", "run"] = "own",
    ) -> Iterable[RunResourceView]:
        """Resources produced in the requested scope."""
        with self._session_factory_required()() as session:
            rows = self._resource_repo_required().list_for_task_scope(
                session,
                run_id=self.run_id,
                task_id=self.task_id,
                scope=scope,
            )
        return [RunResourceView.from_row(row) for row in rows]

    def _assert_descendant(self, task_id: UUID) -> None:
        with self._session_factory_required()() as session:
            is_descendant = self._task_inspect_required().is_descendant(
                session,
                run_id=self.run_id,
                ancestor_task_id=self.task_id,
                candidate_task_id=task_id,
            )
        if not is_descendant:
            raise ContainmentViolation(target=task_id, ancestor=self.task_id, run_id=self.run_id)

    def _task_mgmt_required(self) -> Any:  # slopcop: ignore[no-typing-any]
        if self._task_mgmt is None:
            raise RuntimeError("WorkerContext task management service is not configured")
        return self._task_mgmt

    def _task_inspect_required(self) -> Any:  # slopcop: ignore[no-typing-any]
        if self._task_inspect is None:
            raise RuntimeError("WorkerContext task inspection service is not configured")
        return self._task_inspect

    def _resource_repo_required(self) -> Any:  # slopcop: ignore[no-typing-any]
        if self._resource_repo is None:
            raise RuntimeError("WorkerContext resource repository is not configured")
        return self._resource_repo

    def _session_factory_required(self) -> Callable[[], AbstractContextManager[Any]]:
        if self._session_factory is None:
            raise RuntimeError("WorkerContext session factory is not configured")
        return self._session_factory
