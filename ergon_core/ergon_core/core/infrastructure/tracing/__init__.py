"""Tracing facade.

The runtime emits structured spans through this package while keeping the
existing public import path stable:

    from ergon_core.core.infrastructure.tracing import get_trace_sink

Target span hierarchy (one trace per run, keyed by run_id)::

    workflow.execute (synthetic root)
    |   cohort_id, instance_count
    +-- workflow.start
    +-- task.execute (per task)
    |   instance_key
    |   +-- sandbox.setup
    |   +-- worker.execute
    |   |   +-- tool.{tool_name} (per tool call in GenerationTurn)
    |   +-- persist.outputs
    |   +-- evaluation.task (per evaluator)
    |       +-- evaluation.criterion (per criterion)
    +-- task.propagate (per completion)
    +-- communication.message (per ThreadMessage, optional)
    +-- workflow.complete OR workflow.failed

Every span stores relational IDs (run_id, task_id, execution_id, evaluator_id)
for PG lookup, not payload copies. See otel_tracing_v2.md for full attribute
schemas per span.
"""

from ergon_core.core.infrastructure.tracing.attributes import (
    datetime_to_nanos,
    normalize_attributes,
    safe_json_attribute,
    truncate_text,
)
from ergon_core.core.infrastructure.tracing.contexts import (
    evaluation_criterion_context,
    evaluation_task_context,
    persist_outputs_context,
    sandbox_setup_context,
    task_execute_context,
    task_propagate_context,
    workflow_complete_context,
    workflow_failed_context,
    workflow_root_context,
    workflow_start_context,
    worker_execute_context,
)
from ergon_core.core.infrastructure.tracing.ids import (
    DeterministicIdGenerator,
    span_id_from_key,
    trace_id_from_run_id,
)
from ergon_core.core.infrastructure.tracing.noop import NoopTraceSink
from ergon_core.core.infrastructure.tracing.otel import OtelTraceSink
from ergon_core.core.infrastructure.tracing.sinks import get_trace_sink
from ergon_core.core.infrastructure.tracing.types import CompletedSpan, SpanEvent, TraceContext, TraceSink

__all__ = [
    "CompletedSpan",
    "DeterministicIdGenerator",
    "NoopTraceSink",
    "OtelTraceSink",
    "SpanEvent",
    "TraceContext",
    "TraceSink",
    "datetime_to_nanos",
    "evaluation_criterion_context",
    "evaluation_task_context",
    "get_trace_sink",
    "normalize_attributes",
    "persist_outputs_context",
    "safe_json_attribute",
    "sandbox_setup_context",
    "span_id_from_key",
    "task_execute_context",
    "task_propagate_context",
    "trace_id_from_run_id",
    "truncate_text",
    "workflow_complete_context",
    "workflow_failed_context",
    "workflow_root_context",
    "workflow_start_context",
    "worker_execute_context",
]
