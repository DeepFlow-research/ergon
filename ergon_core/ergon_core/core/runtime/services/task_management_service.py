"""TaskManagementService — dynamic delegation of sub-tasks at runtime.

Implements add_task, abandon_task, and refine_task as graph-native
operations. No ExperimentDefinitionTask rows are created; the
RunGraphNode itself carries all the information prepare() needs.
"""

import logging
from uuid import UUID, uuid4

import inngest
from sqlmodel import Session

from ergon_core.core.persistence.graph.status_conventions import (
    ABANDONED,
    PENDING,
    TERMINAL_STATUSES,
)
from ergon_core.core.runtime.errors.delegation_errors import (
    TaskAlreadyTerminalError,
    TaskNotPendingError,
)
from ergon_core.core.runtime.events.task_events import (
    DYNAMIC_TASK_SENTINEL_ID,
    TaskReadyEvent,
)
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import (
    AbandonTaskCommand,
    AbandonTaskResult,
    AddTaskCommand,
    AddTaskResult,
    RefineTaskCommand,
    RefineTaskResult,
)

logger = logging.getLogger(__name__)

_TASK_META = MutationMeta(actor="manager-worker", reason="delegation decision")
_DYNAMIC_TASK_KEY_PREFIX = "dynamic:"


class TaskManagementService:
    def __init__(self, graph_repo: WorkflowGraphRepository | None = None) -> None:
        self._graph_repo = graph_repo or WorkflowGraphRepository()
        self._graph_repo.add_mutation_listener(dashboard_emitter.graph_mutation)

    # ── add_task ──────────────────────────────────────────────

    def add_task(
        self,
        session: Session,
        command: AddTaskCommand,
    ) -> AddTaskResult:
        """Create a graph node + edge for a dynamic sub-task.

        Algorithm:
        1. Look up parent node to inherit instance_key.
        2. Generate unique task_key: "dynamic:<8-char-hex>"
        3. graph_repo.add_node() with worker_binding_key on the node
        4. graph_repo.add_edge(parent -> child)
        5. commit
        6. Return result (caller fires task/ready AFTER this returns)
        """
        node_uuid = uuid4()
        task_key = f"{_DYNAMIC_TASK_KEY_PREFIX}{node_uuid.hex[:8]}"

        parent_node = self._graph_repo.get_node(
            session, command.run_id, command.parent_node_id
        )

        node = self._graph_repo.add_node(
            session,
            command.run_id,
            task_key=task_key,
            instance_key=parent_node.instance_key,
            description=command.description,
            status=PENDING,
            assigned_worker_key=command.worker_binding_key,
            meta=_TASK_META,
        )

        edge = self._graph_repo.add_edge(
            session,
            command.run_id,
            source_node_id=command.parent_node_id,
            target_node_id=node.id,
            status="active",
            meta=_TASK_META,
        )

        session.commit()

        logger.info(
            "add_task: created dynamic node %s (key=%s) under parent %s",
            node.id,
            task_key,
            command.parent_node_id,
        )

        return AddTaskResult(
            node_id=node.id,
            edge_id=edge.id,
            task_key=task_key,
            status=PENDING,
        )

    async def dispatch_task_ready(
        self,
        *,
        run_id: UUID,
        definition_id: UUID,
        node_id: UUID,
    ) -> None:
        """Fire task/ready Inngest event for a graph-native task.

        Called AFTER commit. Uses the DYNAMIC_TASK_SENTINEL_ID for task_id
        since there is no ExperimentDefinitionTask row.
        """
        event = TaskReadyEvent(
            run_id=run_id,
            definition_id=definition_id,
            task_id=DYNAMIC_TASK_SENTINEL_ID,
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

    # ── abandon_task ──────────────────────────────────────────

    def abandon_task(
        self,
        session: Session,
        command: AbandonTaskCommand,
    ) -> AbandonTaskResult:
        """Mark a sub-task node as abandoned.

        Validates the node is not already terminal. Does NOT fire any
        Inngest event. Running executions for this node will complete
        on their own; results are ignored because the node is abandoned.
        """
        node = self._graph_repo.get_node(session, command.run_id, command.node_id)
        previous_status = node.status

        if previous_status in TERMINAL_STATUSES:
            raise TaskAlreadyTerminalError(command.node_id, previous_status)

        self._graph_repo.update_node_status(
            session,
            command.run_id,
            command.node_id,
            ABANDONED,
            meta=MutationMeta(actor="manager-worker", reason="manager abandoned task"),
        )
        session.commit()

        logger.info(
            "abandon_task: node %s status %s -> abandoned",
            command.node_id,
            previous_status,
        )

        return AbandonTaskResult(
            node_id=command.node_id,
            previous_status=previous_status,
            new_status=ABANDONED,
        )

    # ── refine_task ───────────────────────────────────────────

    def refine_task(
        self,
        session: Session,
        command: RefineTaskCommand,
    ) -> RefineTaskResult:
        """Update description on a pending sub-task.

        Only pending nodes can be refined. The graph node's description
        is the single source of truth -- no definition row to keep in sync.
        """
        node = self._graph_repo.get_node(session, command.run_id, command.node_id)
        old_description = node.description

        if node.status != PENDING:
            raise TaskNotPendingError(command.node_id, node.status)

        self._graph_repo.update_node_field(
            session,
            command.run_id,
            command.node_id,
            "description",
            command.new_description,
            meta=MutationMeta(actor="manager-worker", reason="manager refined task"),
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
