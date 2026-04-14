"""Task propagation: resolve DAG dependencies and detect terminal states."""

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.runtime.events.task_events import DYNAMIC_TASK_SENTINEL_ID
from ergon_core.core.runtime.execution.propagation import (
    is_workflow_complete_v2,
    is_workflow_failed_v2,
    on_task_completed_by_node,
)
from ergon_core.core.runtime.services.graph_lookup import GraphNodeLookup
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.orchestration_dto import (
    PropagateTaskCompletionCommand,
    PropagationResult,
    TaskDescriptor,
    WorkflowTerminalState,
)


class TaskPropagationService:
    def propagate(self, command: PropagateTaskCompletionCommand) -> PropagationResult:
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

            newly_ready_node_ids = on_task_completed_by_node(
                session,
                command.run_id,
                node_id,
                command.execution_id,
                graph_repo=graph_repo,
            )

            ready_descriptors: list[TaskDescriptor] = []
            for ready_node_id in newly_ready_node_ids:
                rn = session.get(RunGraphNode, ready_node_id)
                if rn is not None:
                    ready_descriptors.append(
                        TaskDescriptor(
                            task_id=rn.definition_task_id or DYNAMIC_TASK_SENTINEL_ID,
                            task_key=rn.task_key,
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
                workflow_terminal_state=terminal,
            )

    def propagate_failure(self, command: PropagateTaskCompletionCommand) -> PropagationResult:
        with get_session() as session:
            terminal = WorkflowTerminalState.NONE
            if is_workflow_failed_v2(session, command.run_id):
                terminal = WorkflowTerminalState.FAILED

            return PropagationResult(
                run_id=command.run_id,
                definition_id=command.definition_id,
                completed_task_id=command.task_id,
                workflow_terminal_state=terminal,
            )
