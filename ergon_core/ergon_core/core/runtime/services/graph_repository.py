"""WorkflowGraphRepository — single entry point for run graph mutations.

Every mutation method:
1. Validates structural invariants (acyclicity, referential integrity).
2. Writes to run_graph_* tables.
3. Appends to run_graph_mutations in the same transaction.

The repository does NOT validate status transitions or authorization.
Those are the experiment layer's responsibility.
"""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionTaskDependency,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import (
    RunGraphAnnotation,
    RunGraphEdge,
    RunGraphMutation,
    RunGraphNode,
)
from ergon_core.core.persistence.graph.status_conventions import TERMINAL_STATUSES
from ergon_core.core.runtime.errors.graph_errors import (
    CycleError,
    DanglingEdgeError,
    EdgeNotFoundError,
    NodeNotFoundError,
)
from ergon_core.core.runtime.services.graph_dto import (
    AnnotationDeletedMutation,
    AnnotationSetMutation,
    EdgeAddedMutation,
    EdgeRemovedMutation,
    EdgeStatusChangedMutation,
    GraphAnnotationDto,
    GraphEdgeDto,
    GraphMutationDto,
    GraphMutationValue,
    GraphNodeDto,
    MutationMeta,
    NodeAddedMutation,
    NodeFieldChangedMutation,
    NodeRemovedMutation,
    NodeStatusChangedMutation,
    WorkflowGraphDto,
)
from ergon_core.core.utils import utcnow
from sqlmodel import Session, col, select

logger = logging.getLogger(__name__)

# Only fields the execution runtime needs for dispatch live on the core row.
# Everything experiment-specific (payload, contracts, criteria, budgets)
# goes in annotations so the core schema stays domain-agnostic.
_UPDATABLE_NODE_FIELDS = frozenset({"description", "assigned_worker_slug"})


class WorkflowGraphRepository:
    """Mutable DAG with append-only audit log.

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
        self._mutation_listeners: list[Callable[[RunGraphMutation], Awaitable[None]]] = []

    def add_mutation_listener(
        self, listener: Callable[[RunGraphMutation], Awaitable[None]]
    ) -> None:
        self._mutation_listeners.append(listener)

    # ── Initialization ──────────────────────────────────────

    def initialize_from_definition(
        self,
        session: Session,
        run_id: UUID,
        definition_id: UUID,
        *,
        initial_node_status: str,
        initial_edge_status: str,
        task_payload_model: type[BaseModel],
        meta: MutationMeta,
    ) -> WorkflowGraphDto:
        """Copy definition tables into run graph tables.

        Nodes are created with ``initial_node_status`` and edges with
        ``initial_edge_status``. The caller decides what status values
        to use (the core does not interpret them).

        Task payloads from the definition are stored as annotations
        with namespace ``"payload"``.
        """
        now = utcnow()

        instances = list(
            session.exec(
                select(ExperimentDefinitionInstance).where(
                    ExperimentDefinitionInstance.experiment_definition_id == definition_id,
                )
            ).all()
        )
        instance_key_by_id = {i.id: i.instance_key for i in instances}

        tasks = list(
            session.exec(
                select(ExperimentDefinitionTask).where(
                    ExperimentDefinitionTask.experiment_definition_id == definition_id,
                )
            ).all()
        )

        assignments_stmt = select(ExperimentDefinitionTaskAssignment).where(
            ExperimentDefinitionTaskAssignment.experiment_definition_id == definition_id,
        )
        assignments = list(session.exec(assignments_stmt).all())

        workers_stmt = select(ExperimentDefinitionWorker).where(
            ExperimentDefinitionWorker.experiment_definition_id == definition_id,
        )
        worker_type_by_binding = {
            worker.binding_key: worker.worker_type for worker in session.exec(workers_stmt).all()
        }
        worker_by_task: dict[UUID, str] = {}
        for a in assignments:
            worker_by_task[a.task_id] = worker_type_by_binding[a.worker_binding_key]

        deps = list(
            session.exec(
                select(ExperimentDefinitionTaskDependency).where(
                    ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id,
                )
            ).all()
        )

        def_to_node: dict[UUID, UUID] = {}
        node_rows: list[RunGraphNode] = []

        for task in tasks:
            node_id = uuid4()
            def_to_node[task.id] = node_id
            node_rows.append(
                RunGraphNode(
                    id=node_id,
                    run_id=run_id,
                    definition_task_id=task.id,
                    instance_key=instance_key_by_id[task.instance_id],
                    task_slug=task.task_slug,
                    description=task.description,
                    status=initial_node_status,
                    assigned_worker_slug=worker_by_task.get(task.id),
                    created_at=now,
                    updated_at=now,
                )
            )

        edge_rows: list[RunGraphEdge] = []
        for dep in deps:
            edge_rows.append(
                RunGraphEdge(
                    id=uuid4(),
                    run_id=run_id,
                    definition_dependency_id=dep.id,
                    source_node_id=def_to_node[dep.depends_on_task_id],
                    target_node_id=def_to_node[dep.task_id],
                    status=initial_edge_status,
                    created_at=now,
                    updated_at=now,
                )
            )

        session.add_all(node_rows)
        session.add_all(edge_rows)
        session.flush()

        seq = self._next_sequence(session, run_id)

        annotation_rows: list[RunGraphAnnotation] = []
        mutation_rows: list[RunGraphMutation] = []

        for task, node in zip(tasks, node_rows):
            mutation_rows.append(
                RunGraphMutation(
                    run_id=run_id,
                    sequence=seq,
                    mutation_type="node.added",
                    target_type="node",
                    target_id=node.id,
                    actor=meta.actor,
                    old_value=None,
                    new_value=_node_snapshot(node).model_dump(),
                    reason=meta.reason,
                    created_at=now,
                )
            )
            seq += 1

            payload = task.task_payload_as(task_payload_model).model_dump(mode="json")
            if payload:
                annotation_rows.append(
                    RunGraphAnnotation(
                        run_id=run_id,
                        target_type="node",
                        target_id=node.id,
                        namespace="payload",
                        sequence=seq,
                        payload=payload,
                        created_at=now,
                    )
                )
                mutation_rows.append(
                    RunGraphMutation(
                        run_id=run_id,
                        sequence=seq,
                        mutation_type="annotation.set",
                        target_type="node",
                        target_id=node.id,
                        actor=meta.actor,
                        old_value=None,
                        new_value=AnnotationSetMutation(
                            namespace="payload",
                            payload=payload,
                        ).model_dump(),
                        reason=meta.reason,
                        created_at=now,
                    )
                )
                seq += 1

        for edge in edge_rows:
            mutation_rows.append(
                RunGraphMutation(
                    run_id=run_id,
                    sequence=seq,
                    mutation_type="edge.added",
                    target_type="edge",
                    target_id=edge.id,
                    actor=meta.actor,
                    old_value=None,
                    new_value=_edge_snapshot(edge).model_dump(),
                    reason=meta.reason,
                    created_at=now,
                )
            )
            seq += 1

        session.add_all(annotation_rows)
        session.add_all(mutation_rows)
        session.flush()

        return WorkflowGraphDto(
            run_id=run_id,
            nodes=[_to_node_dto(n) for n in node_rows],
            edges=[_to_edge_dto(e) for e in edge_rows],
        )

    # ── Node operations ─────────────────────────────────────

    async def add_node(  # slopcop: ignore[max-function-params]
        self,
        session: Session,
        run_id: UUID,
        *,
        task_slug: str,
        instance_key: str,
        description: str,
        status: str,
        assigned_worker_slug: str | None = None,
        parent_node_id: UUID | None = None,
        level: int = 0,
        meta: MutationMeta,
    ) -> GraphNodeDto:
        """Create a graph node. Writes the containment columns directly.

        parent_node_id and level are set at creation time and never change.
        The caller (TaskManagementService) computes level = parent.level + 1.
        """
        now = utcnow()
        node = RunGraphNode(
            run_id=run_id,
            instance_key=instance_key,
            task_slug=task_slug,
            description=description,
            status=status,
            assigned_worker_slug=assigned_worker_slug,
            parent_node_id=parent_node_id,
            level=level,
            created_at=now,
            updated_at=now,
        )
        session.add(node)
        session.flush()

        await self._log_mutation(
            session,
            run_id,
            mutation_type="node.added",
            target_type="node",
            target_id=node.id,
            meta=meta,
            old_value=None,
            new_value=_node_snapshot(node),
        )
        return _to_node_dto(node)

    async def remove_node(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        terminal_status: str,
        meta: MutationMeta,
    ) -> None:
        node = self._get_node_row(session, run_id, node_id)
        old = _node_removed_snapshot(node)

        connected = list(
            session.exec(
                select(RunGraphEdge).where(
                    RunGraphEdge.run_id == run_id,
                    (RunGraphEdge.source_node_id == node_id)
                    | (RunGraphEdge.target_node_id == node_id),
                )
            ).all()
        )
        for edge in connected:
            await self.remove_edge(
                session,
                run_id=run_id,
                edge_id=edge.id,
                terminal_status=terminal_status,
                meta=meta,
            )

        node.status = terminal_status
        node.updated_at = utcnow()
        session.add(node)
        session.flush()

        await self._log_mutation(
            session,
            run_id,
            mutation_type="node.removed",
            target_type="node",
            target_id=node_id,
            meta=meta,
            old_value=old,
            new_value=_node_removed_snapshot(node),
        )

    async def update_node_status(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        new_status: str,
        meta: MutationMeta,
        only_if_not_terminal: bool = False,
    ) -> bool:
        """Transition a node's status. Returns True if the write applied.

        When ``only_if_not_terminal`` is True, the write is skipped if the
        node is already in a terminal status (COMPLETED, FAILED, CANCELLED).
        This is the single invariant that closes all race conditions in the
        cascade cancellation system — concurrent paths that both attempt to
        write a terminal status resolve to "first writer wins" without
        requiring distributed locks.
        """
        node = self._get_node_row(session, run_id, node_id)

        if only_if_not_terminal and node.status in TERMINAL_STATUSES:
            return False

        old_status = node.status
        node.status = new_status
        node.updated_at = utcnow()
        session.add(node)
        session.flush()

        await self._log_mutation(
            session,
            run_id,
            mutation_type="node.status_changed",
            target_type="node",
            target_id=node_id,
            meta=meta,
            old_value=NodeStatusChangedMutation(status=old_status),
            new_value=NodeStatusChangedMutation(status=new_status),
        )
        return True

    async def update_node_field(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        field: Literal["description", "assigned_worker_slug"],
        value: str | None,
        meta: MutationMeta,
    ) -> GraphNodeDto:
        if field not in _UPDATABLE_NODE_FIELDS:
            raise ValueError(
                f"Field {field!r} is not updatable. Allowed: {sorted(_UPDATABLE_NODE_FIELDS)}"
            )
        node = self._get_node_row(session, run_id, node_id)
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

        await self._log_mutation(
            session,
            run_id,
            mutation_type="node.field_changed",
            target_type="node",
            target_id=node_id,
            meta=meta,
            old_value=NodeFieldChangedMutation(field=field, value=old_value),
            new_value=NodeFieldChangedMutation(field=field, value=value),
        )
        return _to_node_dto(node)

    # ── Edge operations ─────────────────────────────────────

    async def add_edge(
        self,
        session: Session,
        run_id: UUID,
        *,
        source_node_id: UUID,
        target_node_id: UUID,
        status: str,
        meta: MutationMeta,
    ) -> GraphEdgeDto:
        self._require_node_exists(session, run_id, source_node_id)
        self._require_node_exists(session, run_id, target_node_id)
        self._check_no_cycle(session, run_id, source_node_id, target_node_id)

        now = utcnow()
        edge = RunGraphEdge(
            run_id=run_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            status=status,
            created_at=now,
            updated_at=now,
        )
        session.add(edge)
        session.flush()

        await self._log_mutation(
            session,
            run_id,
            mutation_type="edge.added",
            target_type="edge",
            target_id=edge.id,
            meta=meta,
            old_value=None,
            new_value=_edge_snapshot(edge),
        )
        return _to_edge_dto(edge)

    async def remove_edge(
        self,
        session: Session,
        *,
        run_id: UUID,
        edge_id: UUID,
        terminal_status: str,
        meta: MutationMeta,
    ) -> None:
        edge = self._get_edge_row(session, run_id, edge_id)
        old = _edge_removed_snapshot(edge)

        edge.status = terminal_status
        edge.updated_at = utcnow()
        session.add(edge)
        session.flush()

        await self._log_mutation(
            session,
            run_id,
            mutation_type="edge.removed",
            target_type="edge",
            target_id=edge_id,
            meta=meta,
            old_value=old,
            new_value=_edge_removed_snapshot(edge),
        )

    async def update_edge_status(
        self,
        session: Session,
        *,
        run_id: UUID,
        edge_id: UUID,
        new_status: str,
        meta: MutationMeta,
    ) -> GraphEdgeDto:
        edge = self._get_edge_row(session, run_id, edge_id)
        old_status = edge.status

        edge.status = new_status
        edge.updated_at = utcnow()
        session.add(edge)
        session.flush()

        await self._log_mutation(
            session,
            run_id,
            mutation_type="edge.status_changed",
            target_type="edge",
            target_id=edge_id,
            meta=meta,
            old_value=EdgeStatusChangedMutation(status=old_status),
            new_value=EdgeStatusChangedMutation(status=new_status),
        )
        return _to_edge_dto(edge)

    # ── Annotation operations ───────────────────────────────

    async def set_annotation(
        self,
        session: Session,
        run_id: UUID,
        target_type: str,
        target_id: UUID,
        namespace: str,
        payload: dict,
        *,
        meta: MutationMeta,
    ) -> GraphAnnotationDto:
        old_payload = self.get_annotation(session, run_id, target_type, target_id, namespace)
        seq = self._next_sequence(session, run_id)

        row = RunGraphAnnotation(
            run_id=run_id,
            target_type=target_type,
            target_id=target_id,
            namespace=namespace,
            sequence=seq,
            payload=payload,
            created_at=utcnow(),
        )
        session.add(row)
        session.flush()

        await self._log_mutation(
            session,
            run_id,
            mutation_type="annotation.set",
            target_type=target_type,
            target_id=target_id,
            meta=meta,
            old_value=AnnotationSetMutation(namespace=namespace, payload=old_payload)
            if old_payload
            else None,
            new_value=AnnotationSetMutation(namespace=namespace, payload=payload),
        )
        return _to_annotation_dto(row)

    def get_annotation(
        self,
        session: Session,
        run_id: UUID,
        target_type: str,
        target_id: UUID,
        namespace: str,
    ) -> dict | None:
        stmt = (
            select(RunGraphAnnotation.payload)
            .where(
                RunGraphAnnotation.run_id == run_id,
                RunGraphAnnotation.target_type == target_type,
                RunGraphAnnotation.target_id == target_id,
                RunGraphAnnotation.namespace == namespace,
            )
            .order_by(col(RunGraphAnnotation.sequence).desc())
            .limit(1)
        )
        result = session.exec(stmt).first()
        return dict(result) if result is not None else None

    def get_annotation_at(
        self,
        session: Session,
        run_id: UUID,
        target_type: str,
        target_id: UUID,
        namespace: str,
        sequence: int,
    ) -> dict | None:
        """Annotation payload as of a given mutation sequence."""
        stmt = (
            select(RunGraphAnnotation.payload)
            .where(
                RunGraphAnnotation.run_id == run_id,
                RunGraphAnnotation.target_type == target_type,
                RunGraphAnnotation.target_id == target_id,
                RunGraphAnnotation.namespace == namespace,
                RunGraphAnnotation.sequence <= sequence,
            )
            .order_by(col(RunGraphAnnotation.sequence).desc())
            .limit(1)
        )
        result = session.exec(stmt).first()
        return dict(result) if result is not None else None

    def get_annotations(
        self,
        session: Session,
        run_id: UUID,
        target_type: str,
        target_id: UUID,
    ) -> dict[str, dict]:
        """Latest version of all annotations for a target."""
        stmt = (
            select(RunGraphAnnotation)
            .where(
                RunGraphAnnotation.run_id == run_id,
                RunGraphAnnotation.target_type == target_type,
                RunGraphAnnotation.target_id == target_id,
            )
            .order_by(col(RunGraphAnnotation.sequence).desc())
        )
        rows = list(session.exec(stmt).all())

        latest: dict[str, dict] = {}
        for row in rows:
            if row.namespace not in latest:
                latest[row.namespace] = dict(row.payload)
        return latest

    async def delete_annotation(
        self,
        session: Session,
        run_id: UUID,
        target_type: str,
        target_id: UUID,
        namespace: str,
        *,
        meta: MutationMeta,
    ) -> None:
        """Tombstone, not a hard delete. Inserts a row with empty payload so
        the append-only WAL retains complete version history for replay."""
        old_payload = self.get_annotation(session, run_id, target_type, target_id, namespace)
        seq = self._next_sequence(session, run_id)

        row = RunGraphAnnotation(
            run_id=run_id,
            target_type=target_type,
            target_id=target_id,
            namespace=namespace,
            sequence=seq,
            payload={},
            created_at=utcnow(),
        )
        session.add(row)
        session.flush()

        await self._log_mutation(
            session,
            run_id,
            mutation_type="annotation.deleted",
            target_type=target_type,
            target_id=target_id,
            meta=meta,
            old_value=AnnotationDeletedMutation(namespace=namespace, payload=old_payload)
            if old_payload
            else None,
            new_value=AnnotationDeletedMutation(namespace=namespace, payload={}),
        )

    # ── Query operations ────────────────────────────────────

    def get_graph(
        self,
        session: Session,
        run_id: UUID,
    ) -> WorkflowGraphDto:
        nodes = list(session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all())
        edges = list(session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all())
        return WorkflowGraphDto(
            run_id=run_id,
            nodes=[_to_node_dto(n) for n in nodes],
            edges=[_to_edge_dto(e) for e in edges],
        )

    def get_node(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> GraphNodeDto:
        return _to_node_dto(self._get_node_row(session, run_id, node_id))

    def get_edge(
        self,
        session: Session,
        *,
        run_id: UUID,
        edge_id: UUID,
    ) -> GraphEdgeDto:
        return _to_edge_dto(self._get_edge_row(session, run_id, edge_id))

    def get_incoming_edges(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> list[GraphEdgeDto]:
        rows = list(
            session.exec(
                select(RunGraphEdge).where(
                    RunGraphEdge.run_id == run_id,
                    RunGraphEdge.target_node_id == node_id,
                )
            ).all()
        )
        return [_to_edge_dto(e) for e in rows]

    def get_outgoing_edges(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> list[GraphEdgeDto]:
        rows = list(
            session.exec(
                select(RunGraphEdge).where(
                    RunGraphEdge.run_id == run_id,
                    RunGraphEdge.source_node_id == node_id,
                )
            ).all()
        )
        return [_to_edge_dto(e) for e in rows]

    def get_nodes_by_status(
        self,
        session: Session,
        run_id: UUID,
        status: str,
    ) -> list[GraphNodeDto]:
        rows = list(
            session.exec(
                select(RunGraphNode).where(
                    RunGraphNode.run_id == run_id,
                    RunGraphNode.status == status,
                )
            ).all()
        )
        return [_to_node_dto(n) for n in rows]

    def get_mutations(
        self,
        session: Session,
        run_id: UUID,
        *,
        since_sequence: int = 0,
    ) -> list[GraphMutationDto]:
        rows = list(
            session.exec(
                select(RunGraphMutation)
                .where(
                    RunGraphMutation.run_id == run_id,
                    RunGraphMutation.sequence >= since_sequence,
                )
                .order_by(col(RunGraphMutation.sequence).asc())
            ).all()
        )
        return [_to_mutation_dto(m) for m in rows]

    # ── Structural validation ───────────────────────────────

    def validate_acyclic(self, session: Session, run_id: UUID) -> bool:
        edges = list(session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all())
        return _is_acyclic(edges)

    # ── Internal helpers ────────────────────────────────────

    def _get_node_row(
        self,
        session: Session,
        run_id: UUID,
        node_id: UUID,
    ) -> RunGraphNode:
        row = session.exec(
            select(RunGraphNode).where(
                RunGraphNode.id == node_id,
                RunGraphNode.run_id == run_id,
            )
        ).first()
        if row is None:
            raise NodeNotFoundError(node_id, run_id=run_id)
        return row

    def _get_edge_row(
        self,
        session: Session,
        run_id: UUID,
        edge_id: UUID,
    ) -> RunGraphEdge:
        row = session.exec(
            select(RunGraphEdge).where(
                RunGraphEdge.id == edge_id,
                RunGraphEdge.run_id == run_id,
            )
        ).first()
        if row is None:
            raise EdgeNotFoundError(edge_id, run_id=run_id)
        return row

    def _require_node_exists(
        self,
        session: Session,
        run_id: UUID,
        node_id: UUID,
    ) -> None:
        exists = session.exec(
            select(RunGraphNode.id).where(
                RunGraphNode.id == node_id,
                RunGraphNode.run_id == run_id,
            )
        ).first()
        if exists is None:
            raise DanglingEdgeError(
                edge_id=uuid4(),
                missing_node_id=node_id,
                run_id=run_id,
            )

    def _next_sequence(self, session: Session, run_id: UUID) -> int:
        stmt = (
            select(RunGraphMutation.sequence)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(col(RunGraphMutation.sequence).desc())
            .limit(1)
        )
        last = session.exec(stmt).first()
        return (last + 1) if last is not None else 0

    async def _log_mutation(
        self,
        session: Session,
        run_id: UUID,
        *,
        mutation_type: str,
        target_type: str,
        target_id: UUID,
        meta: MutationMeta,
        old_value: GraphMutationValue | None,
        new_value: GraphMutationValue,
    ) -> None:
        seq = self._next_sequence(session, run_id)
        row = RunGraphMutation(
            run_id=run_id,
            sequence=seq,
            mutation_type=mutation_type,
            target_type=target_type,
            target_id=target_id,
            actor=meta.actor,
            old_value=old_value.model_dump() if old_value is not None else None,
            new_value=new_value.model_dump(),
            reason=meta.reason,
            created_at=utcnow(),
        )
        session.add(row)
        session.flush()

        for listener in self._mutation_listeners:
            try:
                await listener(row)
            except Exception:  # slopcop: ignore[no-broad-except]
                logger.warning("Mutation listener failed", exc_info=True)

    def _check_no_cycle(
        self,
        session: Session,
        run_id: UUID,
        source_id: UUID,
        target_id: UUID,
    ) -> None:
        """DFS from target_id following outgoing edges. If we reach
        source_id, adding source→target would create a cycle."""
        edges = list(session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all())
        adj: dict[UUID, list[UUID]] = defaultdict(list)
        for e in edges:
            adj[e.source_node_id].append(e.target_node_id)

        visited: set[UUID] = set()
        stack = [target_id]
        while stack:
            current = stack.pop()
            if current == source_id:
                raise CycleError(source_id, target_id, run_id=run_id)
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adj.get(current, []))


# ---------------------------------------------------------------------------
# DTO conversion helpers
# ---------------------------------------------------------------------------


def _to_node_dto(row: RunGraphNode) -> GraphNodeDto:
    return GraphNodeDto(
        id=row.id,
        run_id=row.run_id,
        definition_task_id=row.definition_task_id,
        instance_key=row.instance_key,
        task_slug=row.task_slug,
        description=row.description,
        status=row.status,
        assigned_worker_slug=row.assigned_worker_slug,
        parent_node_id=row.parent_node_id,
        level=row.level,
    )


def _to_edge_dto(row: RunGraphEdge) -> GraphEdgeDto:
    return GraphEdgeDto(
        id=row.id,
        run_id=row.run_id,
        definition_dependency_id=row.definition_dependency_id,
        source_node_id=row.source_node_id,
        target_node_id=row.target_node_id,
        status=row.status,
    )


def _to_annotation_dto(row: RunGraphAnnotation) -> GraphAnnotationDto:
    return GraphAnnotationDto(
        id=row.id,
        run_id=row.run_id,
        target_type=row.target_type,
        target_id=row.target_id,
        namespace=row.namespace,
        sequence=row.sequence,
        payload=dict(row.payload),
    )


def _to_mutation_dto(row: RunGraphMutation) -> GraphMutationDto:
    return GraphMutationDto(
        id=row.id,
        run_id=row.run_id,
        sequence=row.sequence,
        mutation_type=row.mutation_type,
        target_type=row.target_type,
        target_id=row.target_id,
        actor=row.actor,
        old_value=dict(row.old_value) if row.old_value else None,
        new_value=dict(row.new_value),
        reason=row.reason,
    )


def _node_removed_snapshot(node: RunGraphNode) -> NodeRemovedMutation:
    return NodeRemovedMutation(
        task_slug=node.task_slug,
        instance_key=node.instance_key,
        description=node.description,
        status=node.status,
        assigned_worker_slug=node.assigned_worker_slug,
    )


def _edge_removed_snapshot(edge: RunGraphEdge) -> EdgeRemovedMutation:
    return EdgeRemovedMutation(
        source_node_id=str(edge.source_node_id),
        target_node_id=str(edge.target_node_id),
        status=edge.status,
    )


def _node_snapshot(node: RunGraphNode) -> NodeAddedMutation:
    return NodeAddedMutation(
        task_slug=node.task_slug,
        instance_key=node.instance_key,
        description=node.description,
        status=node.status,
        assigned_worker_slug=node.assigned_worker_slug,
    )


def _edge_snapshot(edge: RunGraphEdge) -> EdgeAddedMutation:
    return EdgeAddedMutation(
        source_node_id=str(edge.source_node_id),
        target_node_id=str(edge.target_node_id),
        status=edge.status,
    )


def _is_acyclic(edges: list[RunGraphEdge]) -> bool:
    """Kahn's algorithm for cycle detection."""
    adj: dict[UUID, list[UUID]] = defaultdict(list)
    in_degree: dict[UUID, int] = defaultdict(int)
    all_nodes: set[UUID] = set()

    for e in edges:
        adj[e.source_node_id].append(e.target_node_id)
        in_degree[e.target_node_id] = in_degree.get(e.target_node_id, 0) + 1
        all_nodes.add(e.source_node_id)
        all_nodes.add(e.target_node_id)

    queue = [n for n in all_nodes if in_degree.get(n, 0) == 0]
    visited = 0

    while queue:
        node = queue.pop()
        visited += 1
        for neighbor in adj.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return visited == len(all_nodes)
