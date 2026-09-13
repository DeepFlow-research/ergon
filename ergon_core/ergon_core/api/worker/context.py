"""Per-execution runtime state passed to Worker.execute()."""

import asyncio
import math
from datetime import timedelta
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, Any, ContextManager, TypeAlias, TypeVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, PrivateAttr

from ergon_core.api.task import Task
from ergon_core.api.errors import ContainmentViolation
from ergon_core.api.worker.results import SpawnedTaskHandle, TaskCompletion
from ergon_core.core.application.runtime.task_models import (
    CancelTaskCommand,
    RefineTaskCommand,
    RestartTaskCommand,
)
from ergon_core.core.application.resources.models import SampleResourceView
from ergon_core.core.application.resources.publishing import (
    CheckpointReference,
    WorkerCheckpointStore,
)
from ergon_core.core.application.runtime.task_models import SubtaskInfo
from ergon_core.core.persistence.shared.types import NodeId, SampleId

if TYPE_CHECKING:
    from sqlmodel import Session

    from ergon_core.core.application.resources.service import SampleResourceReadService
    from ergon_core.core.application.runtime.task_inspection import TaskInspectionService
    from ergon_core.core.application.runtime.task_management import TaskManagementService

    TaskManagementServiceAlias: TypeAlias = TaskManagementService
    TaskInspectionServiceAlias: TypeAlias = TaskInspectionService
    SampleResourceReadServiceAlias: TypeAlias = SampleResourceReadService
    SessionFactory: TypeAlias = Callable[[], ContextManager[Session]]
else:
    TaskManagementServiceAlias: TypeAlias = Any
    TaskInspectionServiceAlias: TypeAlias = Any
    SampleResourceReadServiceAlias: TypeAlias = Any
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
SampleResourceReadServiceDependency: TypeAlias = Annotated[
    SampleResourceReadServiceAlias,
    AfterValidator(_require_injected_dependency),
]
SessionFactoryDependency: TypeAlias = Annotated[
    SessionFactory,
    AfterValidator(_require_injected_dependency),
]


T = TypeVar("T", bound=BaseModel)


class WorkerContext(BaseModel):
    """Runtime context for a single worker execution.

    The facade owns the curated single-target API (``spawn_task``,
    ``cancel_task``, ``refine_task``, ``restart_task``, ``subtasks``,
    ``descendants``, ``get_task``). Containment is enforced: methods
    that target a ``task_id`` raise :class:`ContainmentViolation` if
    the target isn't this context's ``task_id`` or a descendant of it.
    """

    model_config = {"arbitrary_types_allowed": True}

    sample_id: UUID
    task_id: UUID = Field(
        description="SampleGraphNode.task_id — canonical runtime task identity.",
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
    resource_service: SampleResourceReadServiceDependency = Field(
        exclude=True,
        repr=False,
    )
    session_factory: SessionFactoryDependency = Field(exclude=True, repr=False)
    steps: Any | None = Field(default=None, exclude=True, repr=False)
    checkpoint_store: WorkerCheckpointStore | None = Field(default=None, exclude=True, repr=False)
    _wait_index: int = PrivateAttr(default=0)

    @classmethod
    def _for_job(
        cls,
        *,
        sample_id: UUID,
        task_id: UUID,
        execution_id: UUID,
        sandbox_id: str,
        task_mgmt: TaskManagementServiceAlias,
        task_inspect: TaskInspectionServiceAlias,
        resource_service: SampleResourceReadServiceAlias,
        session_factory: SessionFactory,
        steps: Any | None = None,
        checkpoint_store: WorkerCheckpointStore | None = None,
    ) -> "WorkerContext":
        """Construct the job runtime ``WorkerContext``.

        This is the single canonical construction site used by
        ``worker_execute``. Direct construction is still possible, but
        the service dependencies are required there too.
        """

        return cls(
            sample_id=sample_id,
            task_id=task_id,
            execution_id=execution_id,
            sandbox_id=sandbox_id,
            task_mgmt=task_mgmt,
            task_inspect=task_inspect,
            resource_service=resource_service,
            session_factory=session_factory,
            steps=steps,
            checkpoint_store=checkpoint_store,
        )

    # ── facade methods ─────────────────────────────────────────────────

    async def spawn_task(
        self,
        task: Task,
        *,
        depends_on: tuple[UUID, ...] = (),
    ) -> SpawnedTaskHandle:
        """Spawn a child task under this context's task_id."""

        handle = await self.task_mgmt.spawn_dynamic_task(
            sample_id=self.sample_id,
            parent_task_id=self.task_id,
            task=task,
            depends_on=depends_on,
        )
        return handle.model_copy(update={"waiter": self.wait_for_task})

    async def run_step(
        self, name: str, operation: Callable[[], Awaitable[T]], *, output_type: type[T]
    ) -> T:
        """Checkpoint JSON-compatible computation using the native workflow step.

        Use stable names and return a typed result. Do not call task tools or
        other workflow steps inside the operation; execute those after it.
        Runtime jobs retain results as native resource artifacts and checkpoint
        compact references, avoiding the workflow engine's aggregate state limit.
        A call without a workflow context executes directly (e.g. unit tests).
        """
        if self.steps is None:
            return await operation()
        store = self.checkpoint_store
        if store is None:
            return await self.steps.run(name, operation, output_type=output_type)

        async def retain() -> CheckpointReference:
            result = await operation()
            return await asyncio.to_thread(store.save, name, result)

        reference = await self.steps.run(name, retain, output_type=CheckpointReference)
        data = await asyncio.to_thread(store.load, reference)
        return output_type.model_validate_json(data)

    async def wait_for_task(self, task_id: UUID, *, timeout_seconds: float = 300) -> TaskCompletion:
        """Wait durably; recheck persisted state to tolerate missed terminal events."""
        if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise ValueError("Task wait timeout must be finite and nonnegative")
        await self._assert_descendant(task_id)
        if task_id == self.task_id:
            raise ValueError("A task cannot wait for itself")
        index = self._wait_index
        self._wait_index += 1
        prefix = f"wait-{task_id}-{index}"

        async def inspect() -> TaskCompletion:
            with self.session_factory() as session:
                return self.task_inspect.completion(
                    session, sample_id=self.sample_id, task_id=task_id
                )

        state = await self.run_step(f"{prefix}-state-0", inspect, output_type=TaskCompletion)
        deadline = state.checked_at + max(0, timeout_seconds)
        iteration = 0
        while state.status not in {"completed", "failed", "cancelled", "blocked"}:
            remaining = deadline - state.checked_at
            if remaining <= 0:
                return state.model_copy(update={"timed_out": True})
            seconds = min(5, remaining)
            if self.steps is None:
                await asyncio.sleep(seconds)
            else:
                await self.steps.wait_for_event(
                    f"{prefix}-event-{iteration}",
                    event="task/completed",
                    if_exp=f"async.data.task_id == '{task_id}' && async.data.sample_id == '{self.sample_id}'",
                    timeout=timedelta(seconds=seconds),
                )
            iteration += 1
            state = await self.run_step(
                f"{prefix}-state-{iteration}", inspect, output_type=TaskCompletion
            )
        return state

    async def cancel_task(self, task_id: UUID, *, reason: str | None = None) -> None:
        """Cancel a descendant task.

        ``reason`` is currently advisory; ``CancelTaskCommand`` has no
        persisted reason field yet, so this facade accepts it for API
        stability but does not thread it into task metadata.
        """

        del reason
        await self._assert_descendant(task_id)
        with self.session_factory() as session:
            await self.task_mgmt.cancel_task(
                session,
                CancelTaskCommand(sample_id=SampleId(self.sample_id), task_id=NodeId(task_id)),
            )

    async def refine_task(
        self,
        task_id: UUID,
        *,
        description: str,
        replacement: Task | None = None,
        depends_on: tuple[UUID, ...] | None = None,
    ) -> None:
        """Refine a descendant task's description. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        with self.session_factory() as session:
            await self.task_mgmt.refine_task(
                session,
                RefineTaskCommand(
                    sample_id=SampleId(self.sample_id),
                    task_id=NodeId(task_id),
                    new_description=description,
                    replacement=replacement,
                    depends_on=depends_on,
                ),
            )

    async def restart_task(self, task_id: UUID) -> SpawnedTaskHandle:
        """Restart a descendant task. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        with self.session_factory() as session:
            result = await self.task_mgmt.restart_task(
                session,
                RestartTaskCommand(sample_id=SampleId(self.sample_id), task_id=NodeId(task_id)),
            )
        return SpawnedTaskHandle(task_id=result.task_id, waiter=self.wait_for_task)

    async def subtasks(self) -> tuple[SubtaskInfo, ...]:
        """Return the direct children of this context's task_id."""

        with self.session_factory() as session:
            rows = self.task_inspect.list_subtasks(
                session,
                sample_id=self.sample_id,
                parent_task_id=self.task_id,
            )
        return tuple(rows)

    async def descendants(self) -> tuple[SubtaskInfo, ...]:
        """Return the transitive descendants of this context's task_id."""

        descendant_ids = await self.task_inspect.descendant_ids(
            sample_id=self.sample_id,
            root_task_id=self.task_id,
        )
        with self.session_factory() as session:
            return tuple(
                self.task_inspect.get_subtask(
                    session,
                    sample_id=self.sample_id,
                    task_id=task_id,
                )
                for task_id in descendant_ids
            )

    async def get_task(self, task_id: UUID) -> SubtaskInfo:
        """Fetch a descendant task by id. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        with self.session_factory() as session:
            return self.task_inspect.get_subtask(
                session,
                sample_id=self.sample_id,
                task_id=task_id,
            )

    async def resources(
        self,
        *,
        task_id: UUID | None = None,
        execution_id: UUID | None = None,
        kind: str | None = None,
        name: str | None = None,
    ) -> tuple[SampleResourceView, ...]:
        """List resources visible to this worker within the current run.

        Resource access is run-scoped by design: workers may inspect and
        copy artifacts produced by upstream or sibling tasks in the same
        run. Lifecycle methods remain descendant-contained.
        """

        return self.resource_service.list_for_run(
            sample_id=self.sample_id,
            task_id=task_id,
            task_attempt_id=execution_id,
            kind=kind,
            name=name,
        )

    async def read_resource(self, resource_id: UUID) -> bytes:
        """Read a visible resource blob from this run."""

        return self.resource_service.read_bytes(
            sample_id=self.sample_id,
            current_task_id=self.task_id,
            resource_id=resource_id,
        )

    async def _assert_descendant(self, task_id: UUID) -> None:
        """Raise ``ContainmentViolation`` if ``task_id`` is not self.task_id or a descendant."""

        if task_id == self.task_id:
            return
        descendant_ids = await self.task_inspect.descendant_ids(
            sample_id=self.sample_id,
            root_task_id=self.task_id,
        )
        if task_id not in descendant_ids:
            raise ContainmentViolation(
                parent_task_id=self.task_id,
                target_task_id=task_id,
            )
