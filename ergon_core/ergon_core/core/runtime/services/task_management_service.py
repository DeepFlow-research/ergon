"""TaskManagementService — subtask lifecycle operations.

Implements add_subtask, cancel_task, plan_subtasks, and refine_task as
graph-native operations. The service owns the write path for agent-initiated
subtask mutations; read-only queries live in TaskInspectionService.
"""

import logging
from collections import deque
from uuid import UUID, uuid4

import inngest
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    EDGE_PENDING,
    PENDING,
    TERMINAL_STATUSES,
)
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.errors.delegation_errors import (
    CycleDetectedError,
    DuplicateLocalKeyError,
    TaskAlreadyTerminalError,
    TaskNotPendingError,
    UnknownLocalKeyError,
)
from ergon_core.core.runtime.events.task_events import (
    DYNAMIC_TASK_SENTINEL_ID,
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
    SubtaskSpec,
)
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

_MANAGER_META = MutationMeta(actor="manager-worker", reason="manager_decision")
_DYNAMIC_TASK_KEY_PREFIX = "dynamic:"


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

    def add_subtask(
        self,
        session: Session,
        command: AddSubtaskCommand,
    ) -> AddSubtaskResult:
        """Create a subtask node under parent_node_id with dependency edges.

        Sets parent_node_id and level on the node so the containment tree
        is queryable without edge traversal. Wires depends_on as
        dependency edges (source=dep, target=new_node).
        """
        node_uuid = uuid4()
        task_key = f"{_DYNAMIC_TASK_KEY_PREFIX}{node_uuid.hex[:8]}"

        parent = self._graph_repo.get_node(
            session, run_id=command.run_id, node_id=command.parent_node_id
        )

        node = self._graph_repo.add_node(
            session,
            command.run_id,
            task_key=task_key,
            instance_key=parent.instance_key,
            description=command.description,
            status=PENDING,
            assigned_worker_key=command.worker_binding_key,
            parent_node_id=command.parent_node_id,
            level=parent.level + 1,
            meta=_MANAGER_META,
        )

        for dep_node_id in command.depends_on:
            self._graph_repo.add_edge(
                session,
                command.run_id,
                source_node_id=dep_node_id,
                target_node_id=node.id,
                status=EDGE_PENDING,
                meta=_MANAGER_META,
            )

        session.commit()

        logger.info(
            "add_subtask: created node %s (key=%s) under parent %s",
            node.id,
            task_key,
            command.parent_node_id,
        )

        return AddSubtaskResult(
            node_id=node.id,
            task_key=task_key,
            status=PENDING,
        )

    # ── cancel_task ──────────────────────────────────────────

    def cancel_task(
        self,
        session: Session,
        command: CancelTaskCommand,
    ) -> CancelTaskResult:
        """Mark a subtask as CANCELLED and emit TaskCancelledEvent.

        Uses only_if_not_terminal to avoid races. Counts non-terminal
        descendants so the caller knows the cascade scope.
        """
        node = self._graph_repo.get_node(
            session, run_id=command.run_id, node_id=command.node_id
        )
        old_status = node.status

        if old_status in TERMINAL_STATUSES:
            raise TaskAlreadyTerminalError(command.node_id, old_status)

        # The explicit raise above handles the non-concurrent case. The
        # only_if_not_terminal guard below is still required as a safety net:
        # a concurrent cascade could transition the node between our get_node
        # and our update_node_status. The guard makes this a harmless no-op
        # rather than a double-write.
        applied = self._graph_repo.update_node_status(
            session,
            run_id=command.run_id,
            node_id=command.node_id,
            new_status=CANCELLED,
            meta=MutationMeta(actor="manager-worker", reason="manager_decision"),
            only_if_not_terminal=True,
        )

        cascaded = 0
        if applied:
            cascaded = _count_non_terminal_descendants(
                session, command.run_id, command.node_id
            )

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
            inngest_client.send_sync(
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

    def plan_subtasks(
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

        key_to_node_id: dict[str, UUID] = {}
        roots: list[str] = []

        for spec in command.subtasks:
            node_uuid = uuid4()
            task_key = f"{_DYNAMIC_TASK_KEY_PREFIX}{node_uuid.hex[:8]}"

            node = self._graph_repo.add_node(
                session,
                command.run_id,
                task_key=task_key,
                instance_key=parent.instance_key,
                description=spec.description,
                status=PENDING,
                assigned_worker_key=spec.worker_binding_key,
                parent_node_id=command.parent_node_id,
                level=parent.level + 1,
                meta=_MANAGER_META,
            )
            key_to_node_id[spec.local_key] = node.id

            if not spec.depends_on:
                roots.append(spec.local_key)

        for spec in command.subtasks:
            target_id = key_to_node_id[spec.local_key]
            for dep_key in spec.depends_on:
                source_id = key_to_node_id[dep_key]
                self._graph_repo.add_edge(
                    session,
                    command.run_id,
                    source_node_id=source_id,
                    target_node_id=target_id,
                    status=EDGE_PENDING,
                    meta=_MANAGER_META,
                )

        session.commit()

        definition_id = self._resolve_definition_id(session, command.run_id)
        for root_key in roots:
            self._dispatch_task_ready(
                run_id=command.run_id,
                definition_id=definition_id,
                node_id=key_to_node_id[root_key],
            )

        logger.info(
            "plan_subtasks: created %d nodes (%d roots) under parent %s",
            len(command.subtasks),
            len(roots),
            command.parent_node_id,
        )

        return PlanSubtasksResult(
            nodes=key_to_node_id,
            roots=roots,
        )

    # ── refine_task ──────────────────────────────────────────

    def refine_task(
        self,
        session: Session,
        command: RefineTaskCommand,
    ) -> RefineTaskResult:
        """Update description on a pending sub-task.

        Only pending nodes can be refined. The graph node's description
        is the single source of truth -- no definition row to keep in sync.
        """
        node = self._graph_repo.get_node(
            session, run_id=command.run_id, node_id=command.node_id
        )
        old_description = node.description

        if node.status != PENDING:
            raise TaskNotPendingError(command.node_id, node.status)

        self._graph_repo.update_node_field(
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

    # ── Internal helpers ─────────────────────────────────────

    def _validate_plan(self, subtasks: list[SubtaskSpec]) -> None:
        """Check for duplicate keys, unknown references, and cycles."""
        keys = self._check_no_duplicate_keys(subtasks)
        self._check_no_unknown_deps(subtasks, keys)
        self._check_no_cycles(subtasks)

    @staticmethod
    def _check_no_duplicate_keys(subtasks: list[SubtaskSpec]) -> set[str]:
        """Return the set of local_keys, raising on duplicates."""
        keys: set[str] = set()
        for spec in subtasks:
            if spec.local_key in keys:
                raise DuplicateLocalKeyError(spec.local_key)
            keys.add(spec.local_key)
        return keys

    @staticmethod
    def _check_no_unknown_deps(subtasks: list[SubtaskSpec], keys: set[str]) -> None:
        """Raise if any depends_on references a key not in the plan."""
        all_deps: set[str] = set()
        for spec in subtasks:
            all_deps.update(spec.depends_on)
        unknown = sorted(all_deps - keys)
        if unknown:
            raise UnknownLocalKeyError(unknown)

    @staticmethod
    def _check_no_cycles(subtasks: list[SubtaskSpec]) -> None:
        """Kahn's algorithm for cycle detection on the local_key graph."""
        in_degree: dict[str, int] = {spec.local_key: 0 for spec in subtasks}
        adj: dict[str, list[str]] = {spec.local_key: [] for spec in subtasks}
        for spec in subtasks:
            for dep in spec.depends_on:
                adj[dep].append(spec.local_key)
                in_degree[spec.local_key] += 1

        queue = deque(k for k, d in in_degree.items() if d == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited < len(subtasks):
            remaining = [k for k, d in in_degree.items() if d > 0]
            raise CycleDetectedError(remaining)

    def _resolve_definition_id(self, session: Session, run_id: UUID) -> UUID:
        """Read experiment_definition_id from RunRecord.

        Every run references exactly one definition, so this is always
        available. Used to populate event payloads.
        """
        run = session.exec(
            select(RunRecord).where(RunRecord.id == run_id)
        ).first()
        if run is None:
            # Fallback for tests that don't seed RunRecord
            return DYNAMIC_TASK_SENTINEL_ID
        return run.experiment_definition_id

    def _dispatch_task_ready(
        self,
        *,
        run_id: UUID,
        definition_id: UUID,
        node_id: UUID,
    ) -> None:
        """Fire task/ready Inngest event synchronously (after commit)."""
        event = TaskReadyEvent(
            run_id=run_id,
            definition_id=definition_id,
            task_id=DYNAMIC_TASK_SENTINEL_ID,
            node_id=node_id,
        )
        inngest_client.send_sync(
            inngest.Event(
                name=TaskReadyEvent.name,
                data=event.model_dump(mode="json"),
            )
        )
        logger.info(
            "dispatch_task_ready: fired task/ready for node %s",
            node_id,
        )
