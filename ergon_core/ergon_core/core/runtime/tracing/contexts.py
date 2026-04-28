"""Runtime trace context factories.

Context factories produce deterministic ``TraceContext`` objects from
run/task/execution/evaluator UUIDs so span trees are reproducible across
replays.
"""

from uuid import UUID

from ergon_core.core.runtime.tracing.ids import span_id_from_key, trace_id_from_run_id
from ergon_core.core.runtime.tracing.types import TraceContext


def workflow_root_context(run_id: UUID) -> TraceContext:
    tid = trace_id_from_run_id(run_id)
    return TraceContext(
        trace_id=tid,
        span_id=span_id_from_key("workflow", str(run_id)),
        run_id=run_id,
    )


def workflow_start_context(run_id: UUID) -> TraceContext:
    root = workflow_root_context(run_id)
    return TraceContext(
        trace_id=root.trace_id,
        span_id=span_id_from_key("workflow_start", str(run_id)),
        parent_span_id=root.span_id,
        run_id=run_id,
    )


def task_execute_context(run_id: UUID, task_id: UUID) -> TraceContext:
    root = workflow_root_context(run_id)
    return TraceContext(
        trace_id=root.trace_id,
        span_id=span_id_from_key("task_execute", str(run_id), str(task_id)),
        parent_span_id=root.span_id,
        run_id=run_id,
        task_id=task_id,
    )


def sandbox_setup_context(run_id: UUID, task_id: UUID) -> TraceContext:
    parent = task_execute_context(run_id, task_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key("sandbox_setup", str(run_id), str(task_id)),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
    )


def worker_execute_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
) -> TraceContext:
    parent = task_execute_context(run_id, task_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(
            "worker_execute",
            str(run_id),
            str(task_id),
            str(execution_id),
        ),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
    )


def persist_outputs_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
) -> TraceContext:
    parent = task_execute_context(run_id, task_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(
            "persist_outputs",
            str(run_id),
            str(task_id),
            str(execution_id),
        ),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
    )


def task_propagate_context(run_id: UUID, task_id: UUID) -> TraceContext:
    root = workflow_root_context(run_id)
    return TraceContext(
        trace_id=root.trace_id,
        span_id=span_id_from_key("task_propagate", str(run_id), str(task_id)),
        parent_span_id=root.span_id,
        run_id=run_id,
        task_id=task_id,
    )


def workflow_complete_context(run_id: UUID) -> TraceContext:
    root = workflow_root_context(run_id)
    return TraceContext(
        trace_id=root.trace_id,
        span_id=span_id_from_key("workflow_complete", str(run_id)),
        parent_span_id=root.span_id,
        run_id=run_id,
    )


def workflow_failed_context(run_id: UUID) -> TraceContext:
    root = workflow_root_context(run_id)
    return TraceContext(
        trace_id=root.trace_id,
        span_id=span_id_from_key("workflow_failed", str(run_id)),
        parent_span_id=root.span_id,
        run_id=run_id,
    )


def evaluation_task_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    evaluator_id: UUID,
) -> TraceContext:
    parent = task_execute_context(run_id, task_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(
            "evaluation_task",
            str(run_id),
            str(task_id),
            str(execution_id),
            str(evaluator_id),
        ),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        evaluator_id=evaluator_id,
    )


def evaluation_criterion_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    evaluator_id: UUID,
    stage_idx: int,
    criterion_idx: int,
) -> TraceContext:
    parent = evaluation_task_context(run_id, task_id, execution_id, evaluator_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(
            "evaluation_criterion",
            str(run_id),
            str(task_id),
            str(execution_id),
            str(evaluator_id),
            str(stage_idx),
            str(criterion_idx),
        ),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        evaluator_id=evaluator_id,
    )
