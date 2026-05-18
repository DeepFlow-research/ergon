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

import asyncio
from collections.abc import AsyncGenerator
from typing import ClassVar, final

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.domain.generation.context_parts import AssistantTextPart, ContextPartChunk
from ergon_core.core.persistence.graph.status_conventions import TERMINAL_STATUSES
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import (
    AssignedWorkerSlug,
    NodeId,
    RunId,
    TaskSlug,
)
from ergon_core.core.application.tasks.inspection import (
    TaskInspectionService,
)
from ergon_core.core.application.tasks.models import (
    PlanSubtasksCommand,
    SubtaskSpec,
)
from ergon_core.core.application.tasks.management import (
    TaskManagementService,
)
from tests.fixtures.smoke_components.smoke_base.constants import SUBTASK_GRAPH

_CHILD_WAIT_TERMINAL_STATUSES = TERMINAL_STATUSES | {"blocked"}


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

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_child_statuses: dict[str, str] = {}

    @final
    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        if context.node_id is None:
            raise ValueError(f"{type(self).__name__} requires context.node_id")

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
        specs = [self._spec_for(slug, deps, desc) for slug, deps, desc in SUBTASK_GRAPH]
        with get_session() as session:
            result = await TaskManagementService().plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=RunId(context.run_id),
                    parent_task_id=NodeId(context.node_id),
                    subtasks=specs,
                ),
            )

        # --- Turn 2: plan result (post-service-call) ----------------------
        summary = "\n".join(
            f"{slug}: planned (node_id={result.nodes[TaskSlug(slug)]})"
            for slug, _deps, _desc in SUBTASK_GRAPH
        )
        yield ContextPartChunk(
            part=AssistantTextPart(
                content=(
                    f"{type(self).__name__}: 9 subtasks planned "
                    f"(roots={sorted(result.roots)}):\n{summary}"
                ),
            ),
        )

        # --- Turn 3: awaiting children (terminal) -------------------------
        waiting_message = (
            f"{type(self).__name__}: awaiting 9 children -- "
            "runtime will mark parent COMPLETED once wait_all resolves"
        )
        yield ContextPartChunk(
            part=AssistantTextPart(
                content=waiting_message,
            ),
        )

        # Poll until every direct child has reached a terminal status.
        # The evaluators fire on TaskCompletedEvent, so the parent must not
        # return until all children are terminal (otherwise criterion checks
        # like SmokeCriterionBase._check_children_completed fail immediately).
        inspection = TaskInspectionService()
        while True:
            with get_session() as session:
                children = inspection.list_subtasks(
                    session,
                    run_id=context.run_id,
                    parent_task_id=context.node_id,
                )
            if children and all(c.status in _CHILD_WAIT_TERMINAL_STATUSES for c in children):
                self._last_child_statuses = {c.task_slug: c.status for c in children}
                break
            await asyncio.sleep(2)

        non_completed = {
            slug: status
            for slug, status in self._last_child_statuses.items()
            if status != "completed"
        }
        if non_completed:
            yield WorkerOutput(
                output=f"child tasks did not all complete: {non_completed}",
                success=False,
                metadata={"child_statuses": self._last_child_statuses},
            )
            return

        yield WorkerOutput(
            output=waiting_message,
            success=True,
            metadata={"child_statuses": self._last_child_statuses},
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
