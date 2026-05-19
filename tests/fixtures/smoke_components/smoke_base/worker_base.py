"""Abstract smoke parent worker.

``SmokeWorkerBase`` is the immutable topology guard: every per-env smoke
parent inherits from it, sets ``type_slug`` + ``leaf_slug``, and does
nothing else.  ``execute`` is ``@final`` so subclasses cannot alter the
9-subtask DAG; per-slug worker routing is opened via the ``_spec_for``
override hook so the sad-path subclass can send one slug to a failing
leaf without touching topology.

Parent yields 3 ``ContextPartChunk`` objects (planning → planned →
awaiting) so every smoke run exercises the incremental chunk persistence
path at realistic volume.  See
``docs/superpowers/plans/test-refactor/01-fixtures.md §2.3``.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar, final
from uuid import UUID

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.shared.context_parts import AssistantTextPart, ContextPartChunk
from ergon_core.core.persistence.shared.types import (
    AssignedWorkerSlug,
    TaskSlug,
)
from ergon_core.core.application.tasks.models import (
    SubtaskSpec,
)
from tests.fixtures.smoke_components.smoke_base.constants import SUBTASK_GRAPH
from tests.fixtures.smoke_components.smoke_base.dynamic_tasks import smoke_task_from_spec


class SmokeWorkerBase(Worker):
    """Abstract parent.  Subclasses set ``type_slug`` and ``leaf_slug``.

    Topology is locked: ``execute`` is ``@final``; the per-slug routing
    hook is ``_spec_for``.  Subclasses MUST NOT override ``execute``; the
    type checker enforces this.
    """

    # Subclasses set this to the env-specific leaf slug,
    # e.g. ``"researchrubrics-smoke-leaf"``.  ``_spec_for`` returns
    # ``SubtaskSpec(assigned_worker_slug=AssignedWorkerSlug(self.leaf_slug))``
    # by default.
    leaf_slug: ClassVar[str]

    # Driver asserts per-run context chunk count against this constant
    # (see tests/e2e/_asserts.py ``_assert_run_turn_counts``).
    PARENT_TURN_COUNT: ClassVar[int] = 3

    @final
    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        if context.task_id is None:
            raise ValueError(f"{type(self).__name__} requires context.task_id")

        # --- Turn 1: planning announcement (pre-service-call) -------------
        yield ContextPartChunk(
            part=AssistantTextPart(
                content=(
                    f"{type(self).__name__}: planning 9 subtasks "
                    f"(diamond+line+singletons) → leaf slug={self.leaf_slug}"
                ),
            ),
        )

        # Per-slug spec construction goes through ``_spec_for`` so sad-path
        # subclasses can route specific slugs to a different leaf worker
        # without overriding execute (which stays @final).
        planned: dict[TaskSlug, UUID] = {}
        roots: list[TaskSlug] = []
        for slug, deps, desc in SUBTASK_GRAPH:
            spec = self._spec_for(slug, deps, desc)
            child_task = smoke_task_from_spec(
                parent_task=task,
                spec=spec,
                model=self.model,
            )
            dependency_task_ids = tuple(planned[dep] for dep in spec.depends_on)
            handle = await context.spawn_task(child_task, depends_on=dependency_task_ids)
            planned[spec.task_slug] = handle.task_id
            if not spec.depends_on:
                roots.append(spec.task_slug)

        # --- Turn 2: plan result (post-service-call) ----------------------
        summary = "\n".join(
            f"{slug}: planned (task_id={planned[TaskSlug(slug)]})"
            for slug, _deps, _desc in SUBTASK_GRAPH
        )
        yield ContextPartChunk(
            part=AssistantTextPart(
                content=(
                    f"{type(self).__name__}: 9 subtasks planned (roots={sorted(roots)}):\n{summary}"
                ),
            ),
        )

        # --- Turn 3: awaiting children (terminal) -------------------------
        waiting_message = (
            f"{type(self).__name__}: planned 9 children -- criterion will observe child completion"
        )
        yield ContextPartChunk(
            part=AssistantTextPart(
                content=waiting_message,
            ),
        )

        yield WorkerOutput(
            output=waiting_message,
            success=True,
            metadata={
                "planned_children": sorted(str(slug) for slug in planned),
                "child_wait_mode": "criterion",
            },
        )

    def _spec_for(
        self,
        slug: str,
        deps: tuple[str, ...],
        desc: str,
    ) -> SubtaskSpec:
        """Overridable per-slug → (assigned_worker_slug, deps) mapping.

        Default routes every slug to ``self.leaf_slug``.  Sad-path
        subclasses override this to route specific slugs (e.g. ``l_2``)
        to a failing leaf while keeping the 9-subtask topology identical.
        ``execute`` stays ``@final`` so topology is never changed; only
        the leaf binding is.
        """
        return SubtaskSpec(
            task_slug=TaskSlug(slug),
            description=desc,
            assigned_worker_slug=AssignedWorkerSlug(self.leaf_slug),
            depends_on=[TaskSlug(d) for d in deps],
        )
