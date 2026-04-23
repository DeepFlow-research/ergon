"""Task propagation: resolve DAG dependencies and detect terminal states."""

from uuid import UUID

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.runtime.execution.propagation import (
    is_workflow_complete_v2,
    is_workflow_failed_v2,
    on_task_completed_or_failed,
)
from ergon_core.core.runtime.services.graph_lookup import GraphNodeLookup
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.orchestration_dto import (
    PropagateTaskCompletionCommand,
    PropagationResult,
    TaskDescriptor,
    WorkflowTerminalState,
)


class TaskPropagationService:
    """Resolve DAG dependencies after a task reaches a terminal state.

    Separated from the Inngest wrappers so the dependency resolution logic
    is testable without an event loop. Each method opens its own session
    because the caller (an Inngest step function) may retry independently.
    """

    async def propagate(self, command: PropagateTaskCompletionCommand) -> PropagationResult:
        """Handle successful task completion: satisfy deps, cascade invalidations.

        Returns newly-ready tasks (for scheduling) and invalidated targets
        (for emitting task/cancelled events). Uses the graph-native v2 path
        which reads stored containment columns rather than edge traversal.
        """
        with get_session() as session:
            graph_repo = WorkflowGraphRepository()

            node_id = command.node_id
            if node_id is None:
                graph_lookup = GraphNodeLookup(session, command.run_id)
                node_id = graph_lookup.node_id(command.task_id)
                if node_id is None:
                    return PropagationResult(
                        run_id=command.run_id,
                        definition_id=command.definition_id,
                        completed_task_id=command.task_id,
                        workflow_terminal_state=WorkflowTerminalState.NONE,
                    )

            # Mark the triggering node as COMPLETED before propagating edges.
            # on_task_completed_or_failed only updates edges and downstream
            # candidates — the node's own status must be set by the caller.
            await graph_repo.update_node_status(
                session,
                run_id=command.run_id,
                node_id=node_id,
                new_status=TaskExecutionStatus.COMPLETED,
                meta=MutationMeta(
                    actor="system:propagation",
                    reason=f"task {command.task_id} completed",
                ),
                only_if_not_terminal=True,
            )

            newly_ready_node_ids, invalidated_node_ids = await on_task_completed_or_failed(
                session,
                command.run_id,
                node_id,
                TaskExecutionStatus.COMPLETED,
                graph_repo=graph_repo,
            )

            ready_descriptors: list[TaskDescriptor] = []
            for ready_node_id in newly_ready_node_ids:
                rn = session.get(RunGraphNode, ready_node_id)
                if rn is not None:
                    ready_descriptors.append(
                        TaskDescriptor(
                            task_id=rn.definition_task_id,
                            task_slug=rn.task_slug,
                            node_id=ready_node_id,
                        )
                    )

            terminal = WorkflowTerminalState.NONE
            if is_workflow_complete_v2(session, command.run_id):
                terminal = WorkflowTerminalState.COMPLETED
            elif is_workflow_failed_v2(session, command.run_id):
                terminal = WorkflowTerminalState.FAILED

            return PropagationResult(
                run_id=command.run_id,
                definition_id=command.definition_id,
                completed_task_id=command.task_id,
                ready_tasks=ready_descriptors,
                invalidated_targets=invalidated_node_ids,
                workflow_terminal_state=terminal,
            )

    async def operator_unblock(self, *, run_id: UUID, node_id: UUID, reason: str) -> None:
        """Operator action: transition a BLOCKED node back to PENDING.

        BLOCKED is non-terminal so the default only_if_not_terminal guard is
        not needed here, but we write unconditionally so it also works if the
        node was somehow left in another non-terminal state.
        """
        with get_session() as session:
            graph_repo = WorkflowGraphRepository()
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_id,
                new_status=TaskExecutionStatus.PENDING,
                meta=MutationMeta(actor="operator:unblock", reason=reason),
            )
            session.commit()

    async def restart_node(self, *, run_id: UUID, node_id: UUID, reason: str) -> None:
        """Operator action: restart a FAILED node by transitioning it back to PENDING.

        FAILED is terminal, so only_if_not_terminal must NOT be used here —
        this is an explicit operator override that reverses a terminal status.
        """
        with get_session() as session:
            graph_repo = WorkflowGraphRepository()
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_id,
                new_status=TaskExecutionStatus.PENDING,
                meta=MutationMeta(actor="operator:restart", reason=reason),
            )
            session.commit()

    async def propagate_failure(self, command: PropagateTaskCompletionCommand) -> PropagationResult:
        """Handle task failure: invalidate downstream deps, detect workflow terminal.

        Unlike propagate(), never produces newly-ready tasks — a failed source
        only invalidates outgoing edges and marks targets CANCELLED.
        """
        with get_session() as session:
            graph_repo = WorkflowGraphRepository()

            node_id = command.node_id
            if node_id is None:
                graph_lookup = GraphNodeLookup(session, command.run_id)
                node_id = graph_lookup.node_id(command.task_id)

            invalidated_node_ids: list[UUID] = []
            if node_id is not None:
                # Mark the triggering node as FAILED before propagating edges.
                await graph_repo.update_node_status(
                    session,
                    run_id=command.run_id,
                    node_id=node_id,
                    new_status=TaskExecutionStatus.FAILED,
                    meta=MutationMeta(
                        actor="system:propagation",
                        reason=f"task {command.task_id} failed",
                    ),
                    only_if_not_terminal=True,
                )

                _ready, invalidated_node_ids = await on_task_completed_or_failed(
                    session,
                    command.run_id,
                    node_id,
                    TaskExecutionStatus.FAILED,
                    graph_repo=graph_repo,
                )

            terminal = WorkflowTerminalState.NONE
            if is_workflow_failed_v2(session, command.run_id):
                terminal = WorkflowTerminalState.FAILED

            return PropagationResult(
                run_id=command.run_id,
                definition_id=command.definition_id,
                completed_task_id=command.task_id,
                invalidated_targets=invalidated_node_ids,
                workflow_terminal_state=terminal,
            )
