"""Task propagation: resolve DAG dependencies and detect terminal states."""

from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.runtime.execution.propagation import (
    is_workflow_complete,
    is_workflow_failed,
    on_task_completed,
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
            graph_lookup = GraphNodeLookup(session, command.run_id)

            newly_ready_ids = on_task_completed(
                session,
                command.run_id,
                command.definition_id,
                command.task_id,
                command.execution_id,
                graph_repo=graph_repo,
                graph_lookup=graph_lookup,
            )

            ready_descriptors: list[TaskDescriptor] = []
            for tid in newly_ready_ids:
                task = session.get(ExperimentDefinitionTask, tid)
                if task is not None:
                    ready_descriptors.append(
                        TaskDescriptor(
                            task_id=task.id,
                            task_key=task.task_key,
                            parent_task_id=task.parent_task_id,
                        )
                    )

            terminal = WorkflowTerminalState.NONE
            if is_workflow_complete(session, command.run_id, command.definition_id):
                terminal = WorkflowTerminalState.COMPLETED
            elif is_workflow_failed(session, command.run_id, command.definition_id):
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
            if is_workflow_failed(session, command.run_id, command.definition_id):
                terminal = WorkflowTerminalState.FAILED

            return PropagationResult(
                run_id=command.run_id,
                definition_id=command.definition_id,
                completed_task_id=command.task_id,
                workflow_terminal_state=terminal,
            )
