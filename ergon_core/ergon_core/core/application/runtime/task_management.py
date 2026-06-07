"""TaskManagementService owns object-bound task lifecycle mutations.

Dynamic task creation is intentionally object-bound: callers pass a public
``Task`` snapshot to ``spawn_dynamic_task(Task)`` and the runtime persists that
snapshot directly on the sample graph. Slug-only dynamic task APIs are retired so
new runtime nodes cannot be created without the worker, criteria, and payload
invariants carried by the public task object.
"""

from __future__ import annotations

import logging
from uuid import UUID

import inngest
from ergon_core.api.task import Task
from ergon_core.api.worker.results import SpawnedTaskHandle
from ergon_core.core.application.events.service import get_dashboard_event_publisher
from ergon_core.core.application.ports import DashboardEventPublisher
from ergon_core.core.application.samples.events import (
    SampleRuntimeEventRow,
    sample_runtime_event_view_from_row,
)
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.application.runtime.status import (
    BLOCKED,
    CANCELLED,
    COMPLETED,
    EDGE_PENDING,
    PENDING,
    RUNNING,
    TERMINAL_STATUSES,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.runtime.events import (
    RuntimeEventDispatcher,
    TaskReadyDispatcher,
)
from ergon_core.core.application.runtime.task_errors import (
    TaskAlreadyTerminalError,
    TaskNotTerminalError,
    TaskRunningError,
)
from ergon_core.core.application.events import (
    CancelCause,
    PropagationCancelCause,
    TaskCancelledEvent,
)
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.application.runtime.graph_traversal import descendants
from ergon_core.core.application.runtime.models import MutationMeta
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.application.runtime.task_models import (
    CancelTaskCommand,
    CancelOrphansResult,
    CancelTaskResult,
    RefineTaskCommand,
    RefineTaskResult,
    RestartTaskCommand,
    RestartTaskResult,
)
from ergon_core.core.application.runtime.task_execution_repository import TaskExecutionRepository
from ergon_core.core.views.dashboard_events.contracts import DashboardSampleRuntimeEvent
from sqlmodel import Session

logger = logging.getLogger(__name__)

_MANAGER_META = MutationMeta(actor="manager-worker", reason="manager_decision")


def _count_non_terminal_descendants(session: Session, sample_id: UUID, task_id: UUID) -> int:
    """Count non-terminal descendants via iterative BFS on parent_task_id.

    Uses Python-level BFS rather than a recursive CTE so the logic is
    portable across SQLite (tests) and Postgres (production).
    """
    return sum(
        1
        for descendant in descendants(session, sample_id=sample_id, root_task_id=task_id)
        if descendant.status not in TERMINAL_STATUSES
    )


class TaskManagementService:
    """Task lifecycle mutations for manager actions and engine cascades."""

    def __init__(
        self,
        graph_repo: RuntimeGraphRepository | None = None,
        dashboard_publisher: DashboardEventPublisher | None = None,
        dashboard_emitter: object | None = None,
        task_ready_dispatcher: TaskReadyDispatcher | None = None,
    ) -> None:
        self._graph_repo = graph_repo or RuntimeGraphRepository()
        self._task_execution_repo = TaskExecutionRepository()
        self._runtime_events = RuntimeEventDispatcher(task_ready_dispatcher)
        if dashboard_publisher is None and dashboard_emitter is not None:
            self._dashboard_publisher = None
            return
        self._dashboard_publisher = dashboard_publisher or get_dashboard_event_publisher()
        self._graph_repo.add_runtime_event_listener(self._publish_runtime_event)

    async def _publish_runtime_event(self, row: SampleRuntimeEventRow) -> None:
        if self._dashboard_publisher is None:
            return
        await self._dashboard_publisher.publish(
            DashboardSampleRuntimeEvent(event=sample_runtime_event_view_from_row(row))
        )

    # ── spawn_dynamic_task ───────────────────────────────────

    async def spawn_dynamic_task(
        self,
        *,
        sample_id: UUID,
        parent_task_id: UUID,
        task: Task,
        depends_on: tuple[UUID, ...] = (),
    ) -> SpawnedTaskHandle:
        """Insert a dynamic graph node with task JSON.

        Used by WorkerContext.spawn_task to make dynamic subtasks
        graph-native. The full Task snapshot lives in
        sample_graph_nodes.task_json with is_dynamic=True.
        """
        dispatch: tuple[UUID, UUID] | None = None
        with get_session() as session:
            parent = self._graph_repo.get_node(session, sample_id=sample_id, task_id=parent_task_id)
            node = await self._graph_repo.add_node(
                session,
                sample_id,
                task_slug=task.task_slug,
                instance_key=task.instance_key,
                description=task.description,
                status=PENDING,
                assigned_worker_slug=task.worker.type_slug,
                parent_task_id=parent_task_id,
                level=parent.level + 1,
                task_json=task.model_dump(mode="json"),
                is_dynamic=True,
                meta=MutationMeta(actor="worker-context", reason="spawn_task"),
            )
            for dep in depends_on:
                await self._graph_repo.add_edge(
                    session,
                    sample_id,
                    source_task_id=dep,
                    target_task_id=node.task_id,
                    status=EDGE_PENDING,
                    meta=MutationMeta(actor="worker-context", reason="spawn dependency"),
                )
            task_id = node.task_id
            if not depends_on:
                dispatch = (sample_id, task_id)
            session.commit()

        if dispatch is not None:
            await self._runtime_events.dispatch_task_ready(
                sample_id=dispatch[0],
                task_id=dispatch[1],
            )

        return SpawnedTaskHandle(task_id=task_id)

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
        node = self._graph_repo.get_node(
            session, sample_id=command.sample_id, task_id=command.task_id
        )
        old_status = node.status

        if old_status in TERMINAL_STATUSES:
            raise TaskAlreadyTerminalError(command.task_id, old_status)

        # The explicit raise above handles the non-concurrent case. The
        # only_if_not_terminal guard below is still required as a safety net:
        # a concurrent cascade could transition the node between our get_node
        # and our update_node_status. The guard makes this a harmless no-op
        # rather than a double-write.
        applied = await self._graph_repo.update_node_status(
            session,
            sample_id=command.sample_id,
            task_id=command.task_id,
            new_status=CANCELLED,
            meta=_MANAGER_META,
            only_if_not_terminal=True,
        )

        cascaded = 0
        if applied:
            cascaded = _count_non_terminal_descendants(session, command.sample_id, command.task_id)

        session.commit()

        if applied:
            event = self._task_cancelled_event(
                session,
                sample_id=command.sample_id,
                task_id=command.task_id,
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
            command.task_id,
            old_status,
            cascaded,
        )

        return CancelTaskResult(
            task_id=command.task_id,
            old_status=old_status,
            cascaded_count=cascaded,
        )

    async def cancel_orphans(
        self,
        session: Session,
        *,
        sample_id: UUID,
        parent_task_id: UUID,
        cause: PropagationCancelCause,
    ) -> CancelOrphansResult:
        """Cancel every non-terminal containment descendant of parent_task_id."""
        meta = MutationMeta(actor="system:cascade", reason=cause)
        transitioned: list[UUID] = []

        for child in descendants(session, sample_id=sample_id, root_task_id=parent_task_id):
            if child.status in TERMINAL_STATUSES:
                continue
            applied = await self._graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=child.task_id,
                new_status=CANCELLED,
                meta=meta,
                only_if_not_terminal=True,
            )
            if applied:
                transitioned.append(child.task_id)

        events = [
            self._task_cancelled_event(
                session,
                sample_id=sample_id,
                task_id=nid,
                cause=cause,
            )
            for nid in transitioned
        ]
        return CancelOrphansResult(
            parent_task_id=parent_task_id,
            cancelled_task_ids=transitioned,
            events_to_emit=events,
        )

    async def block_pending_descendants(
        self,
        session: Session,
        *,
        sample_id: UUID,
        parent_task_id: UUID,
        cause: str,
    ) -> list[UUID]:
        """Block non-terminal, non-running containment descendants."""
        meta = MutationMeta(actor="system:cascade", reason=cause)
        blocked: list[UUID] = []

        for child in descendants(session, sample_id=sample_id, root_task_id=parent_task_id):
            if child.status == RUNNING or child.status in TERMINAL_STATUSES:
                continue
            applied = await self._graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=child.task_id,
                new_status=BLOCKED,
                meta=meta,
                only_if_not_terminal=True,
            )
            if applied:
                blocked.append(child.task_id)

        return blocked

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
        node = self._graph_repo.get_node(
            session, sample_id=command.sample_id, task_id=command.task_id
        )
        old_description = node.description

        if node.status == RUNNING:
            raise TaskRunningError(command.task_id, node.status)

        await self._graph_repo.update_node_field(
            session,
            sample_id=command.sample_id,
            task_id=command.task_id,
            field="description",
            value=command.new_description,
            meta=_MANAGER_META,
        )
        session.commit()

        logger.info(
            "refine_task: node %s description updated",
            command.task_id,
        )

        return RefineTaskResult(
            task_id=command.task_id,
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

        Before own edges and status are reset, ``_invalidate_downstream``
        cancels non-terminal downstream targets (stale input) and
        recurses into COMPLETED downstream targets (stale output).
        """
        node = self._graph_repo.get_node(
            session, sample_id=command.sample_id, task_id=command.task_id
        )
        old_status = node.status

        if old_status not in TERMINAL_STATUSES:
            raise TaskNotTerminalError(command.task_id, old_status)

        invalidated_task_ids = await self._invalidate_downstream(
            session,
            sample_id=command.sample_id,
            task_id=command.task_id,
        )

        # Reset this node's outgoing edges so they re-satisfy on re-run.
        outgoing = self._graph_repo.get_outgoing_edges(
            session, sample_id=command.sample_id, task_id=command.task_id
        )
        for edge in outgoing:
            if edge.status != EDGE_PENDING:
                await self._graph_repo.update_edge_status(
                    session,
                    sample_id=command.sample_id,
                    edge_id=edge.id,
                    new_status=EDGE_PENDING,
                    meta=_MANAGER_META,
                )

        # Reset the node itself. only_if_not_terminal=False because we
        # explicitly want to transition terminal -> pending here; the
        # check above already rejected non-terminal inputs.
        await self._graph_repo.update_node_status(
            session,
            sample_id=command.sample_id,
            task_id=command.task_id,
            new_status=PENDING,
            meta=_MANAGER_META,
            only_if_not_terminal=False,
        )

        session.commit()
        await self._runtime_events.dispatch_task_ready(
            sample_id=command.sample_id,
            task_id=command.task_id,
        )

        logger.info(
            "restart_task: node %s status %s -> pending (invalidated=%d)",
            command.task_id,
            old_status,
            len(invalidated_task_ids),
        )

        return RestartTaskResult(
            task_id=command.task_id,
            old_status=old_status,
            invalidated_task_ids=invalidated_task_ids,
        )

    # ── Internal helpers ─────────────────────────────────────

    async def _invalidate_downstream(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
    ) -> list[UUID]:
        """Cascade invalidate downstream targets whose input is becoming stale.

        When a node is restarted, its downstream targets may be:

        - Non-terminal (PENDING / READY / RUNNING): they were queued or
          running against the old output. Cancel them; the edge will be
          reset by the caller once we return. PENDING targets will go
          CANCELLED but become eligible for re-activation once upstream
          dependencies re-satisfy.
        - COMPLETED: their output is now stale because it was computed
          from the old version of this node. Cancel them, reset their
          own outgoing edges, and recurse into their downstream so deeper
          COMPLETED descendants are also invalidated.
        - FAILED / CANCELLED: already terminal with no stale output to
          flush. Leave them alone; the edge will still be reset so a
          later restart/re-activation can satisfy it.

        Termination: the graph is a DAG (enforced by dynamic task spawning
        and by _check_no_cycle in add_edge), so recursion on outgoing edges
        is finite.

        Returns the flat list of task_ids that were cancelled during the
        cascade, in visitation order.
        """
        invalidated: list[UUID] = []
        # Stack-based DFS — we need to recurse into COMPLETED targets to
        # reach their deeper COMPLETED descendants.
        stack: list[UUID] = [task_id]
        # Guard against multi-parent re-visits (diamond): if B and C both
        # feed F and B and C are both restarted as a pair, we'd visit F
        # twice. Not a correctness bug (idempotent cancels) but wasteful.
        seen: set[UUID] = set()

        while stack:
            current = stack.pop()
            outgoing = self._graph_repo.get_outgoing_edges(
                session, sample_id=sample_id, task_id=current
            )
            for edge in outgoing:
                target_id = edge.target_task_id
                if target_id in seen:
                    continue
                seen.add(target_id)

                target = self._graph_repo.get_node(session, sample_id=sample_id, task_id=target_id)

                if target.status == COMPLETED:
                    # Stale output — cancel, reset incoming edges (so
                    # other fan-in parents re-satisfy them on their next
                    # completion), reset outgoing edges, then recurse.
                    await self._cancel_for_invalidation(
                        session, sample_id=sample_id, task_id=target_id
                    )
                    invalidated.append(target_id)
                    await self._reset_incoming_edges(
                        session, sample_id=sample_id, task_id=target_id
                    )
                    await self._reset_outgoing_edges(
                        session, sample_id=sample_id, task_id=target_id
                    )
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
                    await self._cancel_for_invalidation(
                        session, sample_id=sample_id, task_id=target_id
                    )
                    invalidated.append(target_id)
                    await self._reset_incoming_edges(
                        session, sample_id=sample_id, task_id=target_id
                    )

        return invalidated

    async def _cancel_for_invalidation(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
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
            sample_id=sample_id,
            task_id=task_id,
            new_status=CANCELLED,
            meta=MutationMeta(
                actor="manager-worker",
                reason="downstream_invalidation",
            ),
            only_if_not_terminal=False,
        )
        event = self._task_cancelled_event(
            session,
            sample_id=sample_id,
            task_id=task_id,
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
        sample_id: UUID,
        task_id: UUID,
    ) -> None:
        """Reset a node's outgoing edges to EDGE_PENDING.

        Called during cascade recursion on COMPLETED targets so their
        downstream edges are ready to re-satisfy when this node is
        eventually re-run (via its own restart or via re-activation).
        """
        outgoing = self._graph_repo.get_outgoing_edges(
            session, sample_id=sample_id, task_id=task_id
        )
        for edge in outgoing:
            if edge.status != EDGE_PENDING:
                await self._graph_repo.update_edge_status(
                    session,
                    sample_id=sample_id,
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
        sample_id: UUID,
        task_id: UUID,
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
        incoming = self._graph_repo.get_incoming_edges(
            session, sample_id=sample_id, task_id=task_id
        )
        for edge in incoming:
            if edge.status != EDGE_PENDING:
                await self._graph_repo.update_edge_status(
                    session,
                    sample_id=sample_id,
                    edge_id=edge.id,
                    new_status=EDGE_PENDING,
                    meta=MutationMeta(
                        actor="manager-worker",
                        reason="downstream_invalidation",
                    ),
                )

    def _task_cancelled_event(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
        cause: CancelCause,
    ) -> TaskCancelledEvent:
        execution = self._task_execution_repo.latest_for_node(session, task_id)
        return TaskCancelledEvent(
            sample_id=sample_id,
            task_id=task_id,
            execution_id=None if execution is None else execution.id,
            cause=cause,
        )
