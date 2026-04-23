"""TaskManagementService — subtask lifecycle operations.

Implements add_subtask, cancel_task, plan_subtasks, and refine_task as
graph-native operations. The service owns the write path for agent-initiated
subtask mutations; read-only queries live in TaskInspectionService.
"""

import logging
from collections import deque
from uuid import UUID

import inngest
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    EDGE_PENDING,
    PENDING,
    RUNNING,
    TERMINAL_STATUSES,
)
from ergon_core.core.persistence.shared.types import NodeId, TaskSlug
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.errors.delegation_errors import (
    CycleDetectedError,
    DuplicateTaskSlugError,
    RunRecordMissingError,
    TaskAlreadyTerminalError,
    TaskNotTerminalError,
    TaskRunningError,
    UnknownTaskSlugError,
)
from ergon_core.core.runtime.events.task_events import (
    TaskCancelledEvent,
    TaskReadyEvent,
)
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import (
    AddSubtaskCommand,
    AddSubtaskResult,
    CancelTaskCommand,
    CancelTaskResult,
    PlanSubtasksCommand,
    PlanSubtasksResult,
    RefineTaskCommand,
    RefineTaskResult,
    RestartTaskCommand,
    RestartTaskResult,
    SubtaskSpec,
)
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

_MANAGER_META = MutationMeta(actor="manager-worker", reason="manager_decision")


def _count_non_terminal_descendants(session: Session, run_id: UUID, node_id: UUID) -> int:
    """Count non-terminal descendants via iterative BFS on parent_node_id.

    Uses Python-level BFS rather than a recursive CTE so the logic is
    portable across SQLite (tests) and Postgres (production).
    """
    count = 0
    queue: deque[UUID] = deque([node_id])
    while queue:
        parent = queue.popleft()
        children = session.exec(
            select(RunGraphNode.id, RunGraphNode.status).where(
                RunGraphNode.run_id == run_id,
                RunGraphNode.parent_node_id == parent,
            )
        ).all()
        for child_id, child_status in children:
            if child_status not in TERMINAL_STATUSES:
                count += 1
            queue.append(child_id)
    return count


def _latest_execution_id(session: Session, node_id: UUID) -> UUID | None:
    """Most recent execution for a node, or None.

    Used to attach execution_id to TaskCancelledEvent so the cleanup
    function can release the correct sandbox.
    """
    # reason: deferred to avoid circular import at module level
    from ergon_core.core.persistence.telemetry.models import RunTaskExecution

    exe = session.exec(
        select(RunTaskExecution.id)
        .where(RunTaskExecution.node_id == node_id)
        .order_by(RunTaskExecution.started_at.desc())  # type: ignore[union-attr]
        .limit(1)
    ).first()
    return exe


class TaskManagementService:
    """Agent-initiated subtask lifecycle operations.

    Separated from TaskInspectionService (read-only) and
    SubtaskCancellationService (engine-driven cascade) because this
    service is the only one called from agent tool closures during
    the manager's ReAct loop.
    """

    def __init__(self, graph_repo: WorkflowGraphRepository | None = None) -> None:
        self._graph_repo = graph_repo or WorkflowGraphRepository()
        self._graph_repo.add_mutation_listener(dashboard_emitter.graph_mutation)

    # ── add_subtask ──────────────────────────────────────────

    async def add_subtask(
        self,
        session: Session,
        command: AddSubtaskCommand,
    ) -> AddSubtaskResult:
        """Create a subtask node under parent_node_id with dependency edges.

        Sets parent_node_id and level on the node so the containment tree
        is queryable without edge traversal. Wires depends_on as
        dependency edges (source=dep, target=new_node).
        """
        task_slug = command.task_slug

        parent = self._graph_repo.get_node(
            session, run_id=command.run_id, node_id=command.parent_node_id
        )

        node = await self._graph_repo.add_node(
            session,
            command.run_id,
            task_slug=task_slug,
            instance_key=parent.instance_key,
            description=command.description,
            status=PENDING,
            assigned_worker_slug=command.assigned_worker_slug,
            parent_node_id=command.parent_node_id,
            level=parent.level + 1,
            meta=_MANAGER_META,
        )

        for dep_node_id in command.depends_on:
            await self._graph_repo.add_edge(
                session,
                command.run_id,
                source_node_id=dep_node_id,
                target_node_id=node.id,
                status=EDGE_PENDING,
                meta=_MANAGER_META,
            )

        session.commit()

        logger.info(
            "add_subtask: created node %s (slug=%s) under parent %s",
            node.id,
            task_slug,
            command.parent_node_id,
        )

        return AddSubtaskResult(
            node_id=node.id,
            task_slug=task_slug,
            status=PENDING,
        )

    # ── cancel_task ──────────────────────────────────────────

    async def cancel_task(
        self,
        session: Session,
        command: CancelTaskCommand,
    ) -> CancelTaskResult:
        """Mark a subtask as CANCELLED and emit TaskCancelledEvent.

        Uses only_if_not_terminal to avoid races. Counts non-terminal
        descendants so the caller knows the cascade scope.
        """
        node = self._graph_repo.get_node(session, run_id=command.run_id, node_id=command.node_id)
        old_status = node.status

        if old_status in TERMINAL_STATUSES:
            raise TaskAlreadyTerminalError(command.node_id, old_status)

        # The explicit raise above handles the non-concurrent case. The
        # only_if_not_terminal guard below is still required as a safety net:
        # a concurrent cascade could transition the node between our get_node
        # and our update_node_status. The guard makes this a harmless no-op
        # rather than a double-write.
        applied = await self._graph_repo.update_node_status(
            session,
            run_id=command.run_id,
            node_id=command.node_id,
            new_status=CANCELLED,
            meta=_MANAGER_META,
            only_if_not_terminal=True,
        )

        cascaded = 0
        if applied:
            cascaded = _count_non_terminal_descendants(session, command.run_id, command.node_id)

        session.commit()

        if applied:
            definition_id = self._resolve_definition_id(session, command.run_id)
            execution_id = _latest_execution_id(session, command.node_id)
            event = TaskCancelledEvent(
                run_id=command.run_id,
                definition_id=definition_id,
                node_id=command.node_id,
                execution_id=execution_id,
                cause="manager_decision",
            )
            await inngest_client.send(
                inngest.Event(
                    name=TaskCancelledEvent.name,
                    data=event.model_dump(mode="json"),
                )
            )

        logger.info(
            "cancel_task: node %s status %s -> cancelled (cascaded=%d)",
            command.node_id,
            old_status,
            cascaded,
        )

        return CancelTaskResult(
            node_id=command.node_id,
            old_status=old_status,
            cascaded_count=cascaded,
        )

    # ── plan_subtasks ────────────────────────────────────────

    async def plan_subtasks(
        self,
        session: Session,
        command: PlanSubtasksCommand,
    ) -> PlanSubtasksResult:
        """Batch-create subtasks with local dependency references.

        Validates the plan (no duplicates, no unknown refs, no cycles),
        creates all nodes and edges in one transaction, then dispatches
        root tasks (those with no depends_on).
        """
        self._validate_plan(command.subtasks)

        parent = self._graph_repo.get_node(
            session, run_id=command.run_id, node_id=command.parent_node_id
        )

        slug_to_node_id: dict[TaskSlug, NodeId] = {}
        roots: list[TaskSlug] = []

        for spec in command.subtasks:
            task_slug = spec.task_slug

            node = await self._graph_repo.add_node(
                session,
                command.run_id,
                task_slug=task_slug,
                instance_key=parent.instance_key,
                description=spec.description,
                status=PENDING,
                assigned_worker_slug=spec.assigned_worker_slug,
                parent_node_id=command.parent_node_id,
                level=parent.level + 1,
                meta=_MANAGER_META,
            )
            slug_to_node_id[spec.task_slug] = node.id

            if not spec.depends_on:
                roots.append(spec.task_slug)

        for spec in command.subtasks:
            target_id = slug_to_node_id[spec.task_slug]
            for dep_slug in spec.depends_on:
                source_id = slug_to_node_id[dep_slug]
                await self._graph_repo.add_edge(
                    session,
                    command.run_id,
                    source_node_id=source_id,
                    target_node_id=target_id,
                    status=EDGE_PENDING,
                    meta=_MANAGER_META,
                )

        session.commit()

        definition_id = self._resolve_definition_id(session, command.run_id)
        for root_slug in roots:
            await self._dispatch_task_ready(
                run_id=command.run_id,
                definition_id=definition_id,
                node_id=slug_to_node_id[root_slug],
            )

        logger.info(
            "plan_subtasks: created %d nodes (%d roots) under parent %s",
            len(command.subtasks),
            len(roots),
            command.parent_node_id,
        )

        return PlanSubtasksResult(
            nodes=slug_to_node_id,
            roots=roots,
        )

    # ── refine_task ──────────────────────────────────────────

    async def refine_task(
        self,
        session: Session,
        command: RefineTaskCommand,
    ) -> RefineTaskResult:
        """Update description on a sub-task that is not currently RUNNING.

        Refinement is allowed on PENDING, COMPLETED, FAILED, and CANCELLED
        nodes — this supports the edit-then-rerun flow (``refine_task``
        followed by ``restart_task``). RUNNING is blocked because a worker
        is actively consuming the description and editing it mid-flight
        would produce inconsistent behaviour.

        The graph node's description is the single source of truth --
        no definition row to keep in sync.
        """
        node = self._graph_repo.get_node(session, run_id=command.run_id, node_id=command.node_id)
        old_description = node.description

        if node.status == RUNNING:
            raise TaskRunningError(command.node_id, node.status)

        await self._graph_repo.update_node_field(
            session,
            run_id=command.run_id,
            node_id=command.node_id,
            field="description",
            value=command.new_description,
            meta=_MANAGER_META,
        )
        session.commit()

        logger.info(
            "refine_task: node %s description updated",
            command.node_id,
        )

        return RefineTaskResult(
            node_id=command.node_id,
            old_description=old_description,
            new_description=command.new_description,
        )

    # ── restart_task ─────────────────────────────────────────

    async def restart_task(
        self,
        session: Session,
        command: RestartTaskCommand,
    ) -> RestartTaskResult:
        """Reset a terminal node back to PENDING and re-dispatch task/ready.

        Only nodes in a terminal status (COMPLETED, FAILED, CANCELLED) may
        be restarted. The outgoing dependency edges are reset to
        EDGE_PENDING so that, when this node completes again, normal
        propagation re-satisfies them.

        In this Phase 1 implementation, downstream invalidation is NOT
        yet performed — Phase 2 wires in ``_invalidate_downstream`` which
        cancels non-terminal downstream targets (their input is about to
        change) and recurses into COMPLETED downstream targets (their
        output is now stale).
        """
        node = self._graph_repo.get_node(session, run_id=command.run_id, node_id=command.node_id)
        old_status = node.status

        if old_status not in TERMINAL_STATUSES:
            raise TaskNotTerminalError(command.node_id, old_status)

        # Phase 2 hook: invalidate downstream targets before resetting own
        # edges. Currently a no-op; replaced in Phase 2.
        invalidated_node_ids = await self._invalidate_downstream(
            session,
            run_id=command.run_id,
            node_id=command.node_id,
        )

        # Reset this node's outgoing edges so they re-satisfy on re-run.
        outgoing = self._graph_repo.get_outgoing_edges(
            session, run_id=command.run_id, node_id=command.node_id
        )
        for edge in outgoing:
            if edge.status != EDGE_PENDING:
                await self._graph_repo.update_edge_status(
                    session,
                    run_id=command.run_id,
                    edge_id=edge.id,
                    new_status=EDGE_PENDING,
                    meta=_MANAGER_META,
                )

        # Reset the node itself. only_if_not_terminal=False because we
        # explicitly want to transition terminal -> pending here; the
        # check above already rejected non-terminal inputs.
        await self._graph_repo.update_node_status(
            session,
            run_id=command.run_id,
            node_id=command.node_id,
            new_status=PENDING,
            meta=_MANAGER_META,
            only_if_not_terminal=False,
        )

        session.commit()

        definition_id = self._resolve_definition_id(session, command.run_id)
        await self._dispatch_task_ready(
            run_id=command.run_id,
            definition_id=definition_id,
            node_id=command.node_id,
        )

        logger.info(
            "restart_task: node %s status %s -> pending (invalidated=%d)",
            command.node_id,
            old_status,
            len(invalidated_node_ids),
        )

        return RestartTaskResult(
            node_id=command.node_id,
            old_status=old_status,
            invalidated_node_ids=invalidated_node_ids,
        )

    # ── Internal helpers ─────────────────────────────────────

    async def _invalidate_downstream(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> list[UUID]:
        """Cascade invalidate downstream targets whose input is becoming stale.

        When a node is restarted, its downstream targets may be:

        - Non-terminal (PENDING / READY / RUNNING): they were queued or
          running against the old output. Cancel them; the edge will be
          reset by the caller once we return. PENDING targets will go
          CANCELLED but become eligible for re-activation once deps
          re-satisfy (Phase 3).
        - COMPLETED: their output is now stale because it was computed
          from the old version of this node. Cancel them, reset their
          own outgoing edges, and recurse into their downstream so deeper
          COMPLETED descendants are also invalidated.
        - FAILED / CANCELLED: already terminal with no stale output to
          flush. Leave them alone; the edge will still be reset so a
          later restart/re-activation can satisfy it.

        Termination: the graph is a DAG (enforced by Kahn's algorithm in
        plan_subtasks and by _check_no_cycle in add_edge), so recursion
        on outgoing edges is finite.

        Returns the flat list of node_ids that were cancelled during the
        cascade, in visitation order.
        """
        invalidated: list[UUID] = []
        # Stack-based DFS — we need to recurse into COMPLETED targets to
        # reach their deeper COMPLETED descendants.
        stack: list[UUID] = [node_id]
        # Guard against multi-parent re-visits (diamond): if B and C both
        # feed F and B and C are both restarted as a pair, we'd visit F
        # twice. Not a correctness bug (idempotent cancels) but wasteful.
        seen: set[UUID] = set()

        while stack:
            current = stack.pop()
            outgoing = self._graph_repo.get_outgoing_edges(session, run_id=run_id, node_id=current)
            for edge in outgoing:
                target_id = edge.target_node_id
                if target_id in seen:
                    continue
                seen.add(target_id)

                target = self._graph_repo.get_node(session, run_id=run_id, node_id=target_id)

                if target.status == COMPLETED:
                    # Stale output — cancel, reset incoming edges (so
                    # other fan-in parents re-satisfy them on their next
                    # completion), reset outgoing edges, then recurse.
                    await self._cancel_for_invalidation(session, run_id=run_id, node_id=target_id)
                    invalidated.append(target_id)
                    await self._reset_incoming_edges(session, run_id=run_id, node_id=target_id)
                    await self._reset_outgoing_edges(session, run_id=run_id, node_id=target_id)
                    stack.append(target_id)
                elif target.status in TERMINAL_STATUSES:
                    # FAILED or CANCELLED — no stale output, no recursion.
                    # Edge to this target will be reset by the caller (for
                    # the initiating node) or by the cascade's
                    # _reset_outgoing_edges on a deeper COMPLETED node.
                    continue
                else:
                    # Non-terminal (PENDING / READY / RUNNING) — stale
                    # input. Cancel it. Reset incoming edges so fan-in
                    # siblings must re-satisfy them before the target
                    # re-activates. Do NOT recurse into outgoing: the
                    # target never completed, so no stale downstream.
                    await self._cancel_for_invalidation(session, run_id=run_id, node_id=target_id)
                    invalidated.append(target_id)
                    await self._reset_incoming_edges(session, run_id=run_id, node_id=target_id)

        return invalidated

    async def _cancel_for_invalidation(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> None:
        """Cancel a node as part of downstream invalidation and emit task/cancelled.

        Uses ``only_if_not_terminal=False`` because the cascade specifically
        needs to transition COMPLETED (stale output) → CANCELLED. The
        caller has already filtered out FAILED / CANCELLED targets (no
        stale output to flush), so the only terminal status we will
        overwrite here is COMPLETED — which is the whole point.
        """
        await self._graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=node_id,
            new_status=CANCELLED,
            meta=MutationMeta(
                actor="manager-worker",
                reason="downstream_invalidation",
            ),
            only_if_not_terminal=False,
        )

        definition_id = self._resolve_definition_id(session, run_id)
        execution_id = _latest_execution_id(session, node_id)
        event = TaskCancelledEvent(
            run_id=run_id,
            definition_id=definition_id,
            node_id=node_id,
            execution_id=execution_id,
            cause="downstream_invalidation",
        )
        await inngest_client.send(
            inngest.Event(
                name=TaskCancelledEvent.name,
                data=event.model_dump(mode="json"),
            )
        )

    async def _reset_outgoing_edges(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> None:
        """Reset a node's outgoing edges to EDGE_PENDING.

        Called during cascade recursion on COMPLETED targets so their
        downstream edges are ready to re-satisfy when this node is
        eventually re-run (via its own restart or via re-activation).
        """
        outgoing = self._graph_repo.get_outgoing_edges(session, run_id=run_id, node_id=node_id)
        for edge in outgoing:
            if edge.status != EDGE_PENDING:
                await self._graph_repo.update_edge_status(
                    session,
                    run_id=run_id,
                    edge_id=edge.id,
                    new_status=EDGE_PENDING,
                    meta=MutationMeta(
                        actor="manager-worker",
                        reason="downstream_invalidation",
                    ),
                )

    async def _reset_incoming_edges(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> None:
        """Reset a node's incoming edges to EDGE_PENDING.

        When a downstream target is cancelled due to invalidation, its
        incoming edges reflect the old generation's satisfaction. Resetting
        them to EDGE_PENDING keeps edge state consistent with the "new
        generation" model: an edge is SATISFIED only when the current
        source completion has propagated to this target.

        Re-activation in propagation is driven by source-node status (not
        edge status), so this does not affect whether the target
        re-activates — it only keeps the edge WAL honest.
        """
        incoming = self._graph_repo.get_incoming_edges(session, run_id=run_id, node_id=node_id)
        for edge in incoming:
            if edge.status != EDGE_PENDING:
                await self._graph_repo.update_edge_status(
                    session,
                    run_id=run_id,
                    edge_id=edge.id,
                    new_status=EDGE_PENDING,
                    meta=MutationMeta(
                        actor="manager-worker",
                        reason="downstream_invalidation",
                    ),
                )

    def _validate_plan(self, subtasks: list[SubtaskSpec]) -> None:
        """Check for duplicate slugs, unknown references, and cycles."""
        slugs = self._check_no_duplicate_slugs(subtasks)
        self._check_no_unknown_deps(subtasks, slugs)
        self._check_no_cycles(subtasks)

    @staticmethod
    def _check_no_duplicate_slugs(subtasks: list[SubtaskSpec]) -> set[TaskSlug]:
        """Return the set of task_slugs, raising on duplicates."""
        slugs: set[TaskSlug] = set()
        for spec in subtasks:
            if spec.task_slug in slugs:
                raise DuplicateTaskSlugError(spec.task_slug)
            slugs.add(spec.task_slug)
        return slugs

    @staticmethod
    def _check_no_unknown_deps(subtasks: list[SubtaskSpec], slugs: set[TaskSlug]) -> None:
        """Raise if any depends_on references a task_slug not in the plan."""
        all_deps: set[TaskSlug] = set()
        for spec in subtasks:
            all_deps.update(spec.depends_on)
        unknown = sorted(all_deps - slugs)
        if unknown:
            raise UnknownTaskSlugError(unknown)

    @staticmethod
    def _check_no_cycles(subtasks: list[SubtaskSpec]) -> None:
        """Kahn's algorithm for cycle detection on the task_slug graph."""
        in_degree: dict[TaskSlug, int] = {spec.task_slug: 0 for spec in subtasks}
        adj: dict[TaskSlug, list[TaskSlug]] = {spec.task_slug: [] for spec in subtasks}
        for spec in subtasks:
            for dep in spec.depends_on:
                adj[dep].append(spec.task_slug)
                in_degree[spec.task_slug] += 1

        queue = deque(slug for slug, d in in_degree.items() if d == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited < len(subtasks):
            remaining = [slug for slug, d in in_degree.items() if d > 0]
            raise CycleDetectedError(remaining)

    def _resolve_definition_id(self, session: Session, run_id: UUID) -> UUID:
        """Read experiment_definition_id from RunRecord.

        Every run references exactly one definition, so a missing RunRecord
        is an invariant violation — callers must always create the RunRecord
        before invoking a service that mutates the run's graph. Tests must
        seed a RunRecord via the integration-tier factories/fixtures.
        """
        run = session.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
        if run is None:
            raise RunRecordMissingError(run_id)
        return run.experiment_definition_id

    async def _dispatch_task_ready(
        self,
        *,
        run_id: UUID,
        definition_id: UUID,
        node_id: UUID,
    ) -> None:
        """Fire task/ready Inngest event (after commit)."""
        event = TaskReadyEvent(
            run_id=run_id,
            definition_id=definition_id,
            task_id=None,
            node_id=node_id,
        )
        await inngest_client.send(
            inngest.Event(
                name=TaskReadyEvent.name,
                data=event.model_dump(mode="json"),
            )
        )
        logger.info(
            "dispatch_task_ready: fired task/ready for node %s",
            node_id,
        )
