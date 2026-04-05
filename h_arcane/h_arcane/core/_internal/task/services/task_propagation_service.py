"""Application service for task completion propagation."""

from __future__ import annotations

from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.tracing import TraceContext, TraceSink
from h_arcane.core._internal.task.propagation import (
    is_workflow_complete,
    is_workflow_failed,
    on_task_completed,
)
from h_arcane.core._internal.task.services.dto import (
    PropagateTaskCompletionCommand,
    PropagationResult,
    TaskDescriptor,
    WorkflowTerminalState,
)


class TaskPropagationService:
    """Advance workflow state after a task completes."""

    def __init__(
        self,
        trace_sink: TraceSink | None = None,
        trace_context: TraceContext | None = None,
    ) -> None:
        self._trace_sink = trace_sink
        self._trace_context = trace_context

    def _add_event(self, name: str, **attributes: object) -> None:
        if self._trace_sink is None or self._trace_context is None:
            return
        self._trace_sink.add_event(self._trace_context, name, dict(attributes))

    def propagate(self, command: PropagateTaskCompletionCommand) -> PropagationResult:
        self._add_event(
            "task_propagation.started",
            run_id=command.run_id,
            task_id=command.task_id,
            execution_id=command.execution_id,
        )
        ready_task_ids = on_task_completed(command.run_id, command.task_id, command.execution_id)

        run = queries.runs.get(command.run_id)
        experiment = queries.experiments.get(command.experiment_id) if run else None
        tree = experiment.parsed_task_tree() if experiment else None

        ready_tasks = []
        for task_id in ready_task_ids:
            task_node = tree.find_by_id(task_id) if tree else None
            ready_tasks.append(
                TaskDescriptor(
                    task_id=task_id,
                    task_name=task_node.name if task_node else f"Task {task_id}",
                    parent_task_id=task_node.parent_id if task_node else None,
                )
            )

        terminal_state = WorkflowTerminalState.NONE
        if is_workflow_complete(command.run_id):
            terminal_state = WorkflowTerminalState.COMPLETED
        elif is_workflow_failed(command.run_id):
            terminal_state = WorkflowTerminalState.FAILED
        self._add_event(
            "task_propagation.completed",
            completed_task_id=command.task_id,
            ready_task_count=len(ready_tasks),
            workflow_terminal_state=terminal_state.value,
        )

        return PropagationResult(
            run_id=command.run_id,
            experiment_id=command.experiment_id,
            completed_task_id=command.task_id,
            ready_tasks=ready_tasks,
            workflow_terminal_state=terminal_state,
        )

    def propagate_failure(self, command: PropagateTaskCompletionCommand) -> PropagationResult:
        """Advance workflow state after a task fails."""
        self._add_event(
            "task_failure_propagation.started",
            run_id=command.run_id,
            task_id=command.task_id,
            execution_id=command.execution_id,
        )

        terminal_state = WorkflowTerminalState.NONE
        if is_workflow_failed(command.run_id):
            terminal_state = WorkflowTerminalState.FAILED

        self._add_event(
            "task_failure_propagation.completed",
            failed_task_id=command.task_id,
            workflow_terminal_state=terminal_state.value,
        )

        return PropagationResult(
            run_id=command.run_id,
            experiment_id=command.experiment_id,
            completed_task_id=command.task_id,
            ready_tasks=[],
            workflow_terminal_state=terminal_state,
        )
