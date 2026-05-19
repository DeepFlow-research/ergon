"""Per-execution runtime state passed to Worker.execute()."""

from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from ergon_core.api.benchmark.task import Task
from ergon_core.api.errors import ContainmentViolation
from ergon_core.api.worker.results import SpawnedTaskHandle
from ergon_core.core.application.resources.models import RunResourceView
from ergon_core.core.application.tasks.models import SubtaskInfo
from ergon_core.core.persistence.shared.types import NodeId, RunId


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

    # Injected services. These are required construction dependencies
    # because WorkerContext is the executable worker-facing facade.
    # They are excluded from dumps so context identity remains plain JSON.
    #
    # Typed as ``Any`` (with a comment naming the
    # real class) to avoid an api → core → api import cycle:
    # ``TaskManagementService`` lives in
    # ``ergon_core.core.application.tasks.management`` which imports
    # ``from ergon_core.api.registry import registry``. Typing the
    # ``PrivateAttr`` with the real class would close that cycle.
    # TODO: I'd quite like these typed as their "real objects," lets find some way to make that happen.
    task_mgmt: Any = Field(
        exclude=True,
        repr=False,
    )  # TaskManagementService — slopcop: ignore[no-typing-any]
    task_inspect: Any = Field(
        exclude=True,
        repr=False,
    )  # TaskInspectionService — slopcop: ignore[no-typing-any]
    resource_repo: Any = Field(
        exclude=True,
        repr=False,
    )  # RunResourceRepository — slopcop: ignore[no-typing-any]
    session_factory: Any = Field(exclude=True, repr=False)  # slopcop: ignore[no-typing-any]

    @model_validator(mode="after")
    def _validate_required_services(self) -> "WorkerContext":
        service_values = {
            "task_mgmt": self.task_mgmt,
            "task_inspect": self.task_inspect,
            "resource_repo": self.resource_repo,
            "session_factory": self.session_factory,
        }
        missing = [name for name, value in service_values.items() if value is None]
        if missing:
            raise ValueError(
                "WorkerContext requires non-null facade services: " + ", ".join(missing)
            )
        return self

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
        task_mgmt: Any,  # TaskManagementService — slopcop: ignore[no-typing-any] # TODO: find some way to strongly type this
        task_inspect: Any,  # TaskInspectionService — slopcop: ignore[no-typing-any] # TODO: find some way to strongly type this
        resource_repo: Any,  # RunResourceRepository — slopcop: ignore[no-typing-any] # TODO: find some way to strongly type this
        session_factory: Any,  # slopcop: ignore[no-typing-any]
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
            node_id=node_id,
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
        depends_on: tuple[
            UUID, ...
        ] = (),  # todo: consider if this should be required and not have a default
    ) -> SpawnedTaskHandle:
        """Spawn a child task under this context's task_id."""

        if self.task_id is None:
            raise RuntimeError(
                "WorkerContext.spawn_task called from a context without "
                "task_id; this is a v2-runtime bug."
            )

        return await self.task_mgmt.spawn_dynamic_task(
            run_id=self.run_id,
            parent_task_id=self.task_id,
            task=task,
            depends_on=depends_on,
        )

    async def cancel_task(
        self, task_id: UUID, *, reason: str = ""
    ) -> None:  # todo: make reason str | None not str = ""
        """Cancel a descendant task.

        ``reason`` is currently advisory; ``CancelTaskCommand`` has no
        persisted reason field yet, so this facade accepts it for API
        stability but does not thread it into task metadata.
        """

        del reason
        await self._assert_descendant(task_id)
        from ergon_core.core.application.tasks.models import CancelTaskCommand

        with self.session_factory() as session:
            await self.task_mgmt.cancel_task(
                session,
                CancelTaskCommand(run_id=RunId(self.run_id), node_id=NodeId(task_id)),
            )

    async def refine_task(self, task_id: UUID, *, description: str) -> None:
        """Refine a descendant task's description. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        from ergon_core.core.application.tasks.models import RefineTaskCommand

        with self.session_factory() as session:
            await self.task_mgmt.refine_task(
                session,
                RefineTaskCommand(
                    run_id=RunId(self.run_id),
                    node_id=NodeId(task_id),
                    new_description=description,
                ),
            )

    async def restart_task(self, task_id: UUID) -> SpawnedTaskHandle:
        """Restart a descendant task. Raises ``ContainmentViolation`` otherwise."""

        await self._assert_descendant(task_id)
        from ergon_core.core.application.tasks.models import RestartTaskCommand

        with self.session_factory() as session:
            result = await self.task_mgmt.restart_task(
                session,
                RestartTaskCommand(run_id=RunId(self.run_id), node_id=NodeId(task_id)),
            )
        return SpawnedTaskHandle(task_id=result.node_id)

    async def subtasks(self) -> tuple[SubtaskInfo, ...]:
        """Return the direct children of this context's task_id."""

        if self.task_id is None:
            return ()
        with self.session_factory() as session:
            rows = self.task_inspect.list_subtasks(
                session,
                run_id=self.run_id,
                parent_node_id=self.task_id,
            )
        return tuple(rows)

    async def descendants(self) -> tuple[SubtaskInfo, ...]:
        """Return the transitive descendants of this context's task_id."""

        if self.task_id is None:
            return ()
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
                node_id=task_id,
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
