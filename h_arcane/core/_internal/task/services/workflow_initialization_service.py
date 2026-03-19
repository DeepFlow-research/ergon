"""Application service for workflow initialization."""

from __future__ import annotations

from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.tracing import TraceContext, TraceSink
from h_arcane.core._internal.task.propagation import get_initial_ready_tasks, mark_task_ready
from h_arcane.core._internal.task.services.dto import (
    InitializeWorkflowCommand,
    InitializedWorkflow,
    TaskDescriptor,
)
from h_arcane.core._internal.utils import require_not_none, utcnow
from h_arcane.core.status import TaskStatus, TaskTrigger


class WorkflowInitializationService:
    """Initialize workflow state before runner-owned event fanout."""

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

    def initialize(self, command: InitializeWorkflowCommand) -> InitializedWorkflow:
        self._add_event(
            "workflow_initialization.started",
            run_id=command.run_id,
            experiment_id=command.experiment_id,
        )
        experiment = require_not_none(
            queries.experiments.get(command.experiment_id),
            f"Experiment {command.experiment_id} not found",
        )
        tree = experiment.parsed_task_tree()
        if tree is None:
            raise ValueError(f"Experiment {command.experiment_id} has no task_tree")

        pending_tasks = [
            TaskDescriptor(
                task_id=task_node.id,
                task_name=task_node.name,
                parent_task_id=task_node.parent_id,
            )
            for task_node in tree.walk()
        ]

        for task in pending_tasks:
            queries.task_state_events.record_state_change(
                run_id=command.run_id,
                task_id=task.task_id,
                new_status=TaskStatus.PENDING,
                old_status=None,
                triggered_by=TaskTrigger.WORKFLOW_STARTED,
            )
        self._add_event("workflow_initialization.pending_tasks_created", count=len(pending_tasks))

        evaluator_count = 0
        for task_id, eval_ref in tree.extract_evaluators():
            evaluator_data = eval_ref.model_dump()
            evaluator_config = dict(evaluator_data)
            evaluator_type = evaluator_config.pop("type", "unknown")
            queries.task_evaluators.create_evaluator(
                run_id=command.run_id,
                task_id=task_id,
                evaluator_type=evaluator_type,
                evaluator_config=evaluator_config,
            )
            evaluator_count += 1
        self._add_event("workflow_initialization.evaluators_created", count=evaluator_count)

        run = queries.runs.get(command.run_id)
        if run:
            run.status = RunStatus.EXECUTING
            run.started_at = utcnow()
            queries.runs.update(run)

        task_by_id = {task.task_id: task for task in pending_tasks}
        initial_ready_ids = get_initial_ready_tasks(command.run_id)
        for task_id in initial_ready_ids:
            mark_task_ready(command.run_id, task_id, triggered_by=TaskTrigger.WORKFLOW_STARTED)
        self._add_event("workflow_initialization.ready_tasks_marked", count=len(initial_ready_ids))

        initial_ready_tasks = [task_by_id[task_id] for task_id in initial_ready_ids if task_id in task_by_id]
        self._add_event(
            "workflow_initialization.completed",
            dependency_count=len(tree.extract_dependencies()),
            evaluator_count=evaluator_count,
            initial_ready_count=len(initial_ready_tasks),
        )

        return InitializedWorkflow(
            run_id=command.run_id,
            experiment_id=command.experiment_id,
            workflow_name=tree.name,
            task_tree=tree,
            dependency_count=len(tree.extract_dependencies()),
            evaluator_count=evaluator_count,
            total_tasks=len(pending_tasks),
            total_leaf_tasks=len(tree.get_leaf_ids()),
            pending_tasks=pending_tasks,
            initial_ready_tasks=initial_ready_tasks,
        )
