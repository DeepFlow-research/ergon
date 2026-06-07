"""RuntimeGraphRepository — single entry point for sample graph writes.

Every write method:
1. Validates structural invariants (acyclicity, referential integrity).
2. Writes to sample_graph_* tables.
3. Appends typed sample runtime WAL rows in the same transaction.

The repository does NOT validate status transitions or authorization.
Those are the experiment layer's responsibility.
"""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.persistence.samples.models import (
    SampleAnnotationEventRow,
    SampleEdgeEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)
from ergon_core.core.application.samples.events import (
    SampleRuntimeEventAppender,
    SampleRuntimeEventRow,
)
from ergon_core.core.application.runtime.status import TERMINAL_STATUSES
from ergon_core.core.application.runtime.errors import (
    CycleError,
    DanglingEdgeError,
    EdgeNotFoundError,
    NodeNotFoundError,
)
from ergon_core.api.task import Task
from ergon_core.core.application.runtime.models import (
    GraphEdgeDto,
    GraphNodeDto,
    MutationMeta,
    SampleGraphNodeView,
    WorkflowGraphDto,
)
from ergon_core.core.shared.utils import utcnow
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

# Only fields the execution runtime needs for dispatch live on the core row.
# Everything experiment-specific (payload, contracts, criteria, budgets)
# goes in annotations so the core schema stays domain-agnostic.
_UPDATABLE_NODE_FIELDS = frozenset({"description", "assigned_worker_slug"})


class RuntimeGraphRepository:
    """Mutable DAG with typed append-only runtime WAL.

    All methods accept a Session for caller-controlled transactions.

    Enforces structural invariants only (acyclicity, referential integrity).
    Does NOT validate status transitions or authorization — those are the
    experiment layer's responsibility. This separation (dependency inversion)
    lets different experiments define different lifecycles and access-control
    policies without changing core code.

    The ``actor`` field in MutationMeta is for audit (who did this), not
    authorization (were they allowed to). The experiment layer enforces
    permissions before calling repository methods.
    """

    def __init__(self) -> None:
        self._runtime_event_listeners: list[Callable[[SampleRuntimeEventRow], Awaitable[None]]] = []

    def add_runtime_event_listener(
        self, listener: Callable[[SampleRuntimeEventRow], Awaitable[None]]
    ) -> None:
        self._runtime_event_listeners.append(listener)

    # ── Initialization ──────────────────────────────────────

    # ── Task operations ─────────────────────────────────────

    async def node(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
        sandbox_id: str | None = None,
    ) -> SampleGraphNodeView:
        """Inflate a typed SampleGraphNodeView from `sample_graph_nodes.task_json`.

        The repository reads only the run-tier ``task_json`` column and
        reconstructs a typed Task via ``Task.from_definition``. The job
        body downstream receives a ``SampleGraphNodeView`` with the Task
        already inflated: no raw JSON and no definition-tier reads.

        Async because ``Task.from_definition`` is async.

        ``SampleGraphNode.task_id`` is the task identity for both
        definition-seeded and dynamic nodes.
        """

        row = session.exec(
            select(SampleGraphNode).where(
                SampleGraphNode.sample_id == sample_id,
                SampleGraphNode.task_id == task_id,
            )
        ).first()
        if row is None:
            raise NodeNotFoundError(task_id, sample_id=sample_id)

        task = await Task.from_definition(
            row.task_json,
            task_id=row.task_id,
            sandbox_id=sandbox_id,
        )
        return SampleGraphNodeView(
            sample_id=row.sample_id,
            task_id=row.task_id,
            parent_task_id=row.parent_task_id,
            status=row.status,
            task=task,
            is_dynamic=row.is_dynamic,
        )

    async def add_node(  # slopcop: ignore[max-function-params]
        self,
        session: Session,
        sample_id: UUID,
        *,
        task_slug: str,
        instance_key: str,
        description: str,
        status: str,
        assigned_worker_slug: str | None = None,
        parent_task_id: UUID | None = None,
        level: int = 0,
        task_json: dict | None = None,
        is_dynamic: bool = True,
        meta: MutationMeta,
    ) -> GraphNodeDto:
        """Create a graph node. Writes the containment columns directly.

        parent_task_id and level are set at creation time and never change.
        The caller (TaskManagementService) computes level = parent.level + 1.

        ``task_json`` and ``is_dynamic`` carry the run-tier task snapshot
        and the static-vs-dynamic discriminator.
        """
        if task_json is None:
            raise ValueError("RuntimeGraphRepository.add_task requires task_json")
        now = utcnow()
        node = SampleGraphNode(
            sample_id=sample_id,
            instance_key=instance_key,
            task_slug=task_slug,
            description=description,
            task_json=task_json,
            is_dynamic=is_dynamic,
            status=status,
            assigned_worker_slug=assigned_worker_slug,
            parent_task_id=parent_task_id,
            level=level,
            created_at=now,
            updated_at=now,
        )
        session.add(node)
        session.flush()

        appender = SampleRuntimeEventAppender(session)
        task_event = appender.append_task_event(
            SampleTaskEventRow(
                sample_id=sample_id,
                task_id=node.task_id,
                task_slug=node.task_slug,
                event_type="task.added",
                status=status,
                actor=meta.actor,
                event_timestamp=now,
                task_snapshot_json=node.task_json,
                payload_json=_task_payload(node),
            )
        )
        await self._publish_runtime_event(task_event)
        for event in self._append_task_component_events(
            appender,
            sample_id=sample_id,
            actor=meta.actor,
            event_timestamp=now,
            task_id=node.task_id,
            task_json=node.task_json,
            assigned_worker_slug=node.assigned_worker_slug,
        ):
            await self._publish_runtime_event(event)
        return _to_node_dto(node)

    async def update_node_status(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
        new_status: str,
        meta: MutationMeta,
        only_if_not_terminal: bool = False,
    ) -> bool:
        """Transition a node's status. Returns True if the write applied.

        When ``only_if_not_terminal`` is True, the write is skipped if the
        task is already in a terminal status (COMPLETED, FAILED, CANCELLED).
        This is the single invariant that closes all race conditions in the
        cascade cancellation system — concurrent paths that both attempt to
        write a terminal status resolve to "first writer wins" without
        requiring distributed locks.
        """
        node = self._get_node_row(session, sample_id, task_id)

        if only_if_not_terminal and node.status in TERMINAL_STATUSES:
            return False

        old_status = node.status
        node.status = new_status
        node.updated_at = utcnow()
        session.add(node)
        session.flush()

        event = SampleRuntimeEventAppender(session).append_task_event(
            SampleTaskEventRow(
                sample_id=sample_id,
                task_id=task_id,
                task_slug=node.task_slug,
                event_type="task.status_changed",
                status=new_status,
                actor=meta.actor,
                payload_json={
                    "old_status": old_status,
                    "status": new_status,
                    "reason": meta.reason,
                },
            )
        )
        await self._publish_runtime_event(event)
        return True

    async def update_node_field(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
        field: Literal["description", "assigned_worker_slug"],
        value: str | None,
        meta: MutationMeta,
    ) -> GraphNodeDto:
        if field not in _UPDATABLE_NODE_FIELDS:
            raise ValueError(
                f"Field {field!r} is not updatable. Allowed: {sorted(_UPDATABLE_NODE_FIELDS)}"
            )
        node = self._get_node_row(session, sample_id, task_id)
        if field == "description":
            if value is None:
                raise ValueError("description cannot be cleared")
            old_value = node.description
            node.description = value
        else:
            old_value = node.assigned_worker_slug
            node.assigned_worker_slug = value
        node.updated_at = utcnow()
        session.add(node)
        session.flush()

        return _to_node_dto(node)

    # ── Edge operations ─────────────────────────────────────

    async def add_edge(
        self,
        session: Session,
        sample_id: UUID,
        *,
        source_task_id: UUID,
        target_task_id: UUID,
        status: str,
        meta: MutationMeta,
    ) -> GraphEdgeDto:
        self._require_node_exists(session, sample_id, source_task_id)
        self._require_node_exists(session, sample_id, target_task_id)
        self._check_no_cycle(session, sample_id, source_task_id, target_task_id)

        now = utcnow()
        edge = SampleGraphEdge(
            sample_id=sample_id,
            source_task_id=source_task_id,
            target_task_id=target_task_id,
            status=status,
            created_at=now,
            updated_at=now,
        )
        session.add(edge)
        session.flush()

        event = SampleRuntimeEventAppender(session).append_edge_event(
            SampleEdgeEventRow(
                sample_id=sample_id,
                edge_id=edge.id,
                source_task_id=edge.source_task_id,
                target_task_id=edge.target_task_id,
                event_type="edge.added",
                status=status,
                actor=meta.actor,
                event_timestamp=now,
                edge_snapshot_json=_edge_payload(edge),
                payload_json=_edge_payload(edge),
            )
        )
        await self._publish_runtime_event(event)
        return _to_edge_dto(edge)

    async def update_edge_status(
        self,
        session: Session,
        *,
        sample_id: UUID,
        edge_id: UUID,
        new_status: str,
        meta: MutationMeta,
    ) -> GraphEdgeDto:
        edge = self._get_edge_row(session, sample_id, edge_id)
        old_status = edge.status

        edge.status = new_status
        edge.updated_at = utcnow()
        session.add(edge)
        session.flush()

        event = SampleRuntimeEventAppender(session).append_edge_event(
            SampleEdgeEventRow(
                sample_id=sample_id,
                edge_id=edge_id,
                source_task_id=edge.source_task_id,
                target_task_id=edge.target_task_id,
                event_type="edge.status_changed",
                status=new_status,
                actor=meta.actor,
                edge_snapshot_json=_edge_payload(edge),
                payload_json={"old_status": old_status, "status": new_status},
            )
        )
        await self._publish_runtime_event(event)
        return _to_edge_dto(edge)

    # ── Query operations ────────────────────────────────────

    def get_node(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
    ) -> GraphNodeDto:
        return _to_node_dto(self._get_node_row(session, sample_id, task_id))

    def get_incoming_edges(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
    ) -> list[GraphEdgeDto]:
        rows = list(
            session.exec(
                select(SampleGraphEdge).where(
                    SampleGraphEdge.sample_id == sample_id,
                    SampleGraphEdge.target_task_id == task_id,
                )
            ).all()
        )
        return [_to_edge_dto(e) for e in rows]

    def get_outgoing_edges(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
    ) -> list[GraphEdgeDto]:
        rows = list(
            session.exec(
                select(SampleGraphEdge).where(
                    SampleGraphEdge.sample_id == sample_id,
                    SampleGraphEdge.source_task_id == task_id,
                )
            ).all()
        )
        return [_to_edge_dto(e) for e in rows]

    # ── Internal helpers ────────────────────────────────────

    def _get_node_row(
        self,
        session: Session,
        sample_id: UUID,
        task_id: UUID,
    ) -> SampleGraphNode:
        row = session.exec(
            select(SampleGraphNode).where(
                SampleGraphNode.task_id == task_id,
                SampleGraphNode.sample_id == sample_id,
            )
        ).first()
        if row is None:
            raise NodeNotFoundError(task_id, sample_id=sample_id)
        return row

    def _get_edge_row(
        self,
        session: Session,
        sample_id: UUID,
        edge_id: UUID,
    ) -> SampleGraphEdge:
        row = session.exec(
            select(SampleGraphEdge).where(
                SampleGraphEdge.id == edge_id,
                SampleGraphEdge.sample_id == sample_id,
            )
        ).first()
        if row is None:
            raise EdgeNotFoundError(edge_id, sample_id=sample_id)
        return row

    def _require_node_exists(
        self,
        session: Session,
        sample_id: UUID,
        task_id: UUID,
    ) -> None:
        exists = session.exec(
            select(SampleGraphNode.task_id).where(
                SampleGraphNode.task_id == task_id,
                SampleGraphNode.sample_id == sample_id,
            )
        ).first()
        if exists is None:
            raise DanglingEdgeError(
                edge_id=uuid4(),
                missing_task_id=task_id,
                sample_id=sample_id,
            )

    def _append_task_component_events(
        self,
        appender: SampleRuntimeEventAppender,
        *,
        sample_id: UUID,
        actor: str,
        event_timestamp: datetime,
        task_id: UUID,
        task_json: dict,
        assigned_worker_slug: str | None,
    ) -> list[SampleRuntimeEventRow]:
        events: list[SampleRuntimeEventRow] = []

        worker_snapshot = _component_snapshot(task_json.get("worker"))
        if worker_snapshot is not None:
            worker_slug = assigned_worker_slug or _component_slug(
                worker_snapshot, fallback="worker"
            )
            events.append(
                appender.append_worker_event(
                    SampleWorkerEventRow(
                        sample_id=sample_id,
                        task_id=task_id,
                        worker_slug=worker_slug,
                        worker_type=_component_type(worker_snapshot, fallback=worker_slug),
                        model_target=_component_model(worker_snapshot),
                        worker_snapshot_json=worker_snapshot,
                        event_type="worker.added",
                        actor=actor,
                        event_timestamp=event_timestamp,
                        payload_json={"worker": worker_snapshot},
                    )
                )
            )

        sandbox_snapshot = _component_snapshot(task_json.get("sandbox"))
        if sandbox_snapshot is not None:
            sandbox_slug = _component_slug(sandbox_snapshot, fallback="sandbox")
            events.append(
                appender.append_sandbox_event(
                    SampleSandboxEventRow(
                        sample_id=sample_id,
                        task_id=task_id,
                        sandbox_slug=sandbox_slug,
                        sandbox_type=_component_type(sandbox_snapshot, fallback=sandbox_slug),
                        sandbox_snapshot_json=sandbox_snapshot,
                        event_type="sandbox.added",
                        actor=actor,
                        event_timestamp=event_timestamp,
                        payload_json={"sandbox": sandbox_snapshot},
                    )
                )
            )

        evaluators = task_json.get("evaluators")
        if isinstance(evaluators, list):
            for evaluator in evaluators:
                evaluator_snapshot = _component_snapshot(evaluator)
                if evaluator_snapshot is None:
                    continue
                evaluator_slug = _component_slug(evaluator_snapshot, fallback="default")
                events.append(
                    appender.append_evaluator_event(
                        SampleEvaluatorEventRow(
                            sample_id=sample_id,
                            task_id=task_id,
                            evaluator_slug=evaluator_slug,
                            evaluator_type=_component_type(
                                evaluator_snapshot,
                                fallback=evaluator_slug,
                            ),
                            evaluator_snapshot_json=evaluator_snapshot,
                            event_type="evaluator.added",
                            actor=actor,
                            event_timestamp=event_timestamp,
                            payload_json={"evaluator": evaluator_snapshot},
                        )
                    )
                )

        return events

    async def _publish_runtime_event(self, row: SampleRuntimeEventRow) -> None:
        for listener in self._runtime_event_listeners:
            try:
                await listener(row)
            except Exception:  # slopcop: ignore[no-broad-except]
                logger.warning("Runtime event listener failed", exc_info=True)

    def _check_no_cycle(
        self,
        session: Session,
        sample_id: UUID,
        source_id: UUID,
        target_id: UUID,
    ) -> None:
        """DFS from target_id following outgoing edges. If we reach
        source_id, adding source→target would create a cycle."""
        edges = list(
            session.exec(
                select(SampleGraphEdge).where(SampleGraphEdge.sample_id == sample_id)
            ).all()
        )
        adj: dict[UUID, list[UUID]] = defaultdict(list)
        for e in edges:
            adj[e.source_task_id].append(e.target_task_id)

        visited: set[UUID] = set()
        stack = [target_id]
        while stack:
            current = stack.pop()
            if current == source_id:
                raise CycleError(source_id, target_id, sample_id=sample_id)
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adj.get(current, []))


# ---------------------------------------------------------------------------
# DTO conversion helpers
# ---------------------------------------------------------------------------


def _to_node_dto(row: SampleGraphNode) -> GraphNodeDto:
    return GraphNodeDto(
        task_id=row.task_id,
        sample_id=row.sample_id,
        instance_key=row.instance_key,
        task_slug=row.task_slug,
        description=row.description,
        status=row.status,
        assigned_worker_slug=row.assigned_worker_slug,
        parent_task_id=row.parent_task_id,
        level=row.level,
    )


def _to_edge_dto(row: SampleGraphEdge) -> GraphEdgeDto:
    return GraphEdgeDto(
        id=row.id,
        sample_id=row.sample_id,
        source_task_id=row.source_task_id,
        target_task_id=row.target_task_id,
        status=row.status,
    )


def _task_payload(node: SampleGraphNode) -> dict:
    return {
        "task_key": node.task_slug,
        "task_slug": node.task_slug,
        "instance_key": node.instance_key,
        "description": node.description,
        "status": node.status,
        "assigned_worker_slug": node.assigned_worker_slug,
        "parent_task_id": str(node.parent_task_id) if node.parent_task_id else None,
        "level": node.level,
        "is_dynamic": node.is_dynamic,
        "task": node.task_json,
    }


def _edge_payload(edge: SampleGraphEdge) -> dict:
    return {
        "source_task_id": str(edge.source_task_id),
        "target_task_id": str(edge.target_task_id),
        "status": edge.status,
    }


def _component_snapshot(value: object) -> dict | None:
    return value if isinstance(value, dict) else None


def _component_slug(snapshot: dict, *, fallback: str) -> str:
    value = snapshot.get("type_slug") or snapshot.get("slug") or snapshot.get("name")
    if isinstance(value, str) and value:
        return value
    component_type = _component_type(snapshot, fallback=fallback)
    return component_type.rsplit(":", 1)[-1].rsplit(".", 1)[-1]


def _component_type(snapshot: dict, *, fallback: str) -> str:
    value = snapshot.get("_type") or snapshot.get("type")
    return value if isinstance(value, str) and value else fallback


def _component_model(snapshot: dict) -> str | None:
    value = snapshot.get("model") or snapshot.get("model_target")
    return value if isinstance(value, str) else None
