"""Per-execution runtime state passed to Worker.execute()."""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, ContextManager, TypeAlias
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field

from ergon_core.api.benchmark.task import Task
from ergon_core.api.errors import ContainmentViolation
from ergon_core.api.worker.results import SpawnedTaskHandle
from ergon_core.core.application.resources.models import RunResourceView
from ergon_core.core.application.tasks.models import SubtaskInfo
from ergon_core.core.persistence.shared.types import NodeId, RunId

if TYPE_CHECKING:
    from sqlmodel import Session

    from ergon_core.core.application.resources.repository import RunResourceRepository
    from ergon_core.core.application.tasks.inspection import TaskInspectionService
    from ergon_core.core.application.tasks.management import TaskManagementService

    TaskManagementServiceAlias: TypeAlias = TaskManagementService
    TaskInspectionServiceAlias: TypeAlias = TaskInspectionService
    RunResourceRepositoryAlias: TypeAlias = RunResourceRepository
    SessionFactory: TypeAlias = Callable[[], ContextManager[Session]]
else:
    TaskManagementServiceAlias: TypeAlias = Any
    TaskInspectionServiceAlias: TypeAlias = Any
    RunResourceRepositoryAlias: TypeAlias = Any
    SessionFactory: TypeAlias = Callable[[], ContextManager[Any]]


def _require_injected_dependency(value: object | None) -> object:
    if value is None:
        raise ValueError("WorkerContext injected dependencies cannot be None")
    return value


TaskManagementDependency: TypeAlias = Annotated[
    TaskManagementServiceAlias,
    AfterValidator(_require_injected_dependency),
]
TaskInspectionDependency: TypeAlias = Annotated[
    TaskInspectionServiceAlias,
    AfterValidator(_require_injected_dependency),
]
RunResourceRepositoryDependency: TypeAlias = Annotated[
    RunResourceRepositoryAlias,
    AfterValidator(_require_injected_dependency),
]
SessionFactoryDependency: TypeAlias = Annotated[
    SessionFactory,
    AfterValidator(_require_injected_dependency),
]


class WorkerContext(BaseModel):
    """Runtime context for a single worker execution.

    The facade owns the curated single-target API (``spawn_task``,
    ``cancel_task``, ``refine_task``, ``restart_task``, ``subtasks``,
    ``descendants``, ``get_task``). Containment is enforced: methods
    that target a ``task_id`` raise :class:`ContainmentViolation` if
    the target isn't this context's ``task_id`` or a descendant of it.
    """

    model_config = {"arbitrary_types_allowed": True}

    run_id: UUID
    task_id: UUID = Field(
        description="RunGraphNode.task_id — canonical runtime task identity.",
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
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Injected services. These are required construction dependencies
    # because WorkerContext is the executable worker-facing facade.
    # They are excluded from dumps so context identity remains plain JSON.
    #
    task_mgmt: TaskManagementDependency = Field(
        exclude=True,
        repr=False,
    )
    task_inspect: TaskInspectionDependency = Field(
        exclude=True,
        repr=False,
    )
    resource_repo: RunResourceRepositoryDependency = Field(
        exclude=True,
        repr=False,
    )
    session_factory: SessionFactoryDependency = Field(exclude=True, repr=False)

    @classmethod
    def _for_job(
        cls,
        *,
        run_id: UUID,
        task_id: UUID,
        execution_id: UUID,
        definition_id: UUID | None,
        sandbox_id: str,
        task_mgmt: TaskManagementServiceAlias,
        task_inspect: TaskInspectionServiceAlias,
        resource_repo: RunResourceRepositoryAlias,
        session_factory: SessionFactory,
    ) -> "WorkerContext":
        """Construct the job runtime ``WorkerContext``.

        This is the single canonical construction site used by
        ``worker_execute``. Direct construction is still possible, but
        the service dependencies are required there too.
        """

        return cls(
            run_id=run_id,
            task_id=task_id,
            execution_id=execution_id,
            definition_id=definition_id,
            sandbox_id=sandbox_id,
            task_mgmt=task_mgmt,
            task_inspect=task_inspect,
            resource_repo=resource_repo,
            session_factory=session_factory,
        )

    # ── facade methods ─────────────────────────────────────────────────

    async def spawn_task(
        self,
        task: Task,
        *,
        depends_on: tuple[UUID, ...] = (),
    ) -> SpawnedTaskHandle:
        """Spawn a child task under this context's task_id."""

        return await self.task_mgmt.spawn_dynamic_task(
            run_id=self.run_id,
            parent_task_id=self.task_id,
            task=task,
            depends_on=depends_on,
        )

    async def cancel_task(self, task_id: UUID, *, reason: str | None = None) -> None:
        """Cancel a descendant task.

        ``reason`` is currently advisory; ``CancelTaskCommand`` has no
        persisted reason field yet, so this facade accepts it for API
        stability but does not thread it into task metadata.
        """

        del reason
        await self._assert_descendant(task_id)
        # reason: keep runtime task command imports out of public API module import time.
        from ergon_core.core.application.tasks.models import CancelTaskCommand

        with self.session_factory() as session:
            await self.task_mgmt.cancel_task(
                session,
                CancelTaskCommand(run_id=RunId(self.run_id), task_id=NodeId(task_id)),
            )

    async def refine_task(self, task_id: UUID, *, description: str) -> None:
        """Refine a descendant task's description. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        # reason: keep runtime task command imports out of public API module import time.
        from ergon_core.core.application.tasks.models import RefineTaskCommand

        with self.session_factory() as session:
            await self.task_mgmt.refine_task(
                session,
                RefineTaskCommand(
                    run_id=RunId(self.run_id),
                    task_id=NodeId(task_id),
                    new_description=description,
                ),
            )

    async def restart_task(self, task_id: UUID) -> SpawnedTaskHandle:
        """Restart a descendant task. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        # reason: keep runtime task command imports out of public API module import time.
        from ergon_core.core.application.tasks.models import RestartTaskCommand

        with self.session_factory() as session:
            result = await self.task_mgmt.restart_task(
                session,
                RestartTaskCommand(run_id=RunId(self.run_id), task_id=NodeId(task_id)),
            )
        return SpawnedTaskHandle(task_id=result.task_id)

    async def subtasks(self) -> tuple[SubtaskInfo, ...]:
        """Return the direct children of this context's task_id."""

        with self.session_factory() as session:
            rows = self.task_inspect.list_subtasks(
                session,
                run_id=self.run_id,
                parent_task_id=self.task_id,
            )
        return tuple(rows)

    async def descendants(self) -> tuple[SubtaskInfo, ...]:
        """Return the transitive descendants of this context's task_id."""

        descendant_ids = await self.task_inspect.descendant_ids(
            run_id=self.run_id,
            root_task_id=self.task_id,
        )
        with self.session_factory() as session:
            return tuple(
                self.task_inspect.get_subtask(
                    session,
                    run_id=self.run_id,
                    node_id=task_id,
                )
                for task_id in descendant_ids
            )

    async def get_task(self, task_id: UUID) -> SubtaskInfo:
        """Fetch a descendant task by id. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        with self.session_factory() as session:
            return self.task_inspect.get_subtask(
                session,
                run_id=self.run_id,
                node_id=task_id,
            )

    async def resources(
        self,
        *,
        task_id: UUID | None = None,
        execution_id: UUID | None = None,
        kind: str | None = None,
        name: str | None = None,
    ) -> tuple[RunResourceView, ...]:
        """List resources visible to this worker within the current run.

        Resource access is run-scoped by design: workers may inspect and
        copy artifacts produced by upstream or sibling tasks in the same
        run. Lifecycle methods remain descendant-contained.
        """

        with self.session_factory() as session:
            rows = self.resource_repo.list_for_run(
                session,
                run_id=self.run_id,
                task_id=task_id,
                task_execution_id=execution_id,
                kind=kind,
                name=name,
            )
        return tuple(rows)

    async def read_resource(self, resource_id: UUID) -> bytes:
        """Read a visible resource blob from this run."""

        with self.session_factory() as session:
            resource = self.resource_repo.get(session, resource_id)
            if resource.run_id != self.run_id:
                raise ContainmentViolation(
                    parent_task_id=self.task_id,
                    target_task_id=resource_id,
                )
            return Path(resource.file_path).read_bytes()

    async def _assert_descendant(self, task_id: UUID) -> None:
        """Raise ``ContainmentViolation`` if ``task_id`` is not self.task_id or a descendant."""

        if task_id == self.task_id:
            return
        descendant_ids = await self.task_inspect.descendant_ids(
            run_id=self.run_id,
            root_task_id=self.task_id,
        )
        if task_id not in descendant_ids:
            raise ContainmentViolation(
                parent_task_id=self.task_id,
                target_task_id=task_id,
            )
