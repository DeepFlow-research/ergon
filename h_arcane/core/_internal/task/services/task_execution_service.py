"""Application service for task execution lifecycle."""

from __future__ import annotations

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.tracing import TraceContext, TraceSink
from h_arcane.core._internal.task.persistence import (
    complete_task_execution,
    create_task_execution,
)
from h_arcane.core._internal.task.propagation import mark_task_failed, mark_task_running
from h_arcane.core._internal.task.services.dto import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PrepareTaskExecutionCommand,
    PreparedTaskExecution,
)
from h_arcane.core._internal.utils import require_not_none


class TaskExecutionService:
    """Prepare and persist task execution state outside the Inngest runner."""

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

    def prepare(self, command: PrepareTaskExecutionCommand) -> PreparedTaskExecution:
        self._add_event(
            "task_execution.prepare.started",
            run_id=command.run_id,
            experiment_id=command.experiment_id,
            task_id=command.task_id,
        )
        run = require_not_none(queries.runs.get(command.run_id), f"Run {command.run_id} not found")
        experiment = require_not_none(
            queries.experiments.get(command.experiment_id),
            f"Experiment {command.experiment_id} not found",
        )

        tree = experiment.parsed_task_tree()
        if not tree:
            raise ValueError(f"Experiment {command.experiment_id} has no task_tree")

        task_node = tree.find_by_id(command.task_id)
        if not task_node:
            raise ValueError(f"Task {command.task_id} not found in task_tree")

        benchmark_name = (
            BenchmarkName(experiment.benchmark_name)
            if isinstance(experiment.benchmark_name, str)
            else experiment.benchmark_name
        )

        if not task_node.is_leaf:
            return PreparedTaskExecution(
                run_id=command.run_id,
                experiment_id=command.experiment_id,
                task_id=command.task_id,
                task_name=task_node.name,
                parent_task_id=task_node.parent_id,
                task_description=task_node.description,
                benchmark_name=benchmark_name.value,
                max_questions=run.max_questions,
                input_resource_ids=[],
                skipped=True,
                skip_reason="composite_task",
            )

        input_resources = queries.resources.get_inputs_for_task(command.experiment_id, command.task_id)
        execution = create_task_execution(command.run_id, command.task_id)
        mark_task_running(command.run_id, command.task_id, execution.id)
        self._add_event(
            "task_execution.prepare.completed",
            task_id=command.task_id,
            execution_id=execution.id,
            input_count=len(input_resources),
        )

        return PreparedTaskExecution(
            run_id=command.run_id,
            experiment_id=command.experiment_id,
            task_id=command.task_id,
            task_name=task_node.name,
            parent_task_id=task_node.parent_id,
            task_description=task_node.description,
            benchmark_name=benchmark_name.value,
            max_questions=run.max_questions,
            input_resource_ids=[resource.id for resource in input_resources],
            execution_id=execution.id,
        )

    def finalize_success(self, command: FinalizeTaskExecutionCommand) -> None:
        self._add_event(
            "task_execution.finalize_success.started",
            execution_id=command.execution_id,
            output_count=len(command.output_resource_ids),
        )
        complete_task_execution(
            execution_id=command.execution_id,
            success=True,
            output_text=command.output_text,
            output_resource_ids=command.output_resource_ids,
        )
        self._add_event(
            "task_execution.finalize_success.completed",
            execution_id=command.execution_id,
            output_count=len(command.output_resource_ids),
        )

    def finalize_failure(self, command: FailTaskExecutionCommand) -> None:
        self._add_event(
            "task_execution.finalize_failure.started",
            execution_id=command.execution_id,
            error=command.error_message,
        )
        mark_task_failed(
            command.run_id,
            command.task_id,
            error=command.error_message,
            execution_id=command.execution_id,
        )
        complete_task_execution(
            execution_id=command.execution_id,
            success=False,
            error_message=command.error_message,
        )
        self._add_event(
            "task_execution.finalize_failure.completed",
            execution_id=command.execution_id,
            error=command.error_message,
        )
