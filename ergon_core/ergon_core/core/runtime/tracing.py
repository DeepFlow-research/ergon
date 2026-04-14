"""Tracing facade.

Defines the TraceSink protocol and data classes that the runtime uses
to emit structured spans. The default sink is NoopTraceSink (discards
everything). When a real backend is wired in (OtelTraceSink), swap the
singleton returned by get_trace_sink().

Context factories at the bottom produce deterministic TraceContext
objects from run/task/execution/evaluator UUIDs so span trees are
reproducible across replays.

Target span hierarchy (one trace per run, keyed by run_id)::

    workflow.execute (synthetic root)
    │   cohort_id, instance_count
    ├── workflow.start
    ├── task.execute (per task)
    │   instance_key
    │   ├── sandbox.setup
    │   ├── worker.execute
    │   │   └── tool.{tool_name} (per tool call in GenerationTurn)
    │   │       turn_index, tool_name, tool_call_id, has_result
    │   ├── persist.outputs
    │   │   resource_ids
    │   └── evaluation.task (per evaluator)
    │       └── evaluation.criterion (per criterion)
    ├── task.propagate (per completion)
    ├── communication.message (per ThreadMessage, optional)
    │   thread_id, from_agent_id, to_agent_id, sequence_num
    └── workflow.complete OR workflow.failed

Every span stores relational IDs (run_id, task_id, execution_id,
evaluator_id) for PG lookup — not payload copies.
See otel_tracing_v2.md for full attribute schemas per span.
"""

import hashlib
import json
import random
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
except ImportError:
    OTLPSpanExporter = None  # type: ignore[assignment,misc]
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    Status,
    StatusCode,
    TraceFlags,
)
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.trace.span import TraceState

from ergon_core.core.settings import settings
from pydantic import BaseModel, Field

TRACE_FLAGS_SAMPLED = 0x01
_MAX_TRACE_ID = (1 << 128) - 1
_MAX_SPAN_ID = (1 << 64) - 1
_EMPTY_SPAN_ID = 0

_desired_trace_id: ContextVar[int | None] = ContextVar("desired_trace_id", default=None)
_desired_span_id: ContextVar[int | None] = ContextVar("desired_span_id", default=None)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class TraceContext(BaseModel):
    model_config = {"frozen": True}

    trace_id: int
    span_id: int
    parent_span_id: int | None = None
    run_id: UUID | None = None
    task_id: UUID | None = None
    execution_id: UUID | None = None
    evaluator_id: UUID | None = None
    attributes: dict[str, object] = Field(default_factory=dict)


class SpanEvent(BaseModel):
    model_config = {"frozen": True}

    name: str
    timestamp: datetime
    attributes: dict[str, object] = Field(default_factory=dict)


class CompletedSpan(BaseModel):
    model_config = {"frozen": True}

    name: str
    context: TraceContext
    start_time: datetime
    end_time: datetime
    attributes: dict[str, object] = Field(default_factory=dict)
    status_code: int = 0
    status_message: str | None = None
    events: list[SpanEvent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TraceSink protocol + noop implementation
# ---------------------------------------------------------------------------


class TraceSink(Protocol):
    def emit_span(self, span: CompletedSpan) -> None: ...

    def add_event(
        self,
        context: TraceContext,
        name: str,
        attributes: dict[str, object] | None = None,
        timestamp: datetime | None = None,
    ) -> None: ...

    def child_context(
        self,
        parent: TraceContext,
        *,
        span_key: str,
        run_id: UUID | None = None,
        task_id: UUID | None = None,
        execution_id: UUID | None = None,
        evaluator_id: UUID | None = None,
        attributes: dict[str, object] | None = None,
    ) -> TraceContext: ...


class NoopTraceSink:
    """Default sink that discards everything. Zero overhead."""

    def emit_span(self, span: CompletedSpan) -> None:
        pass

    def add_event(
        self,
        context: TraceContext,
        name: str,
        attributes: dict[str, object] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        pass

    def child_context(
        self,
        parent: TraceContext,
        *,
        span_key: str,
        run_id: UUID | None = None,
        task_id: UUID | None = None,
        execution_id: UUID | None = None,
        evaluator_id: UUID | None = None,
        attributes: dict[str, object] | None = None,
    ) -> TraceContext:
        child_span = span_id_from_key(str(parent.span_id), span_key)
        return TraceContext(
            trace_id=parent.trace_id,
            span_id=child_span,
            parent_span_id=parent.span_id,
            run_id=run_id or parent.run_id,
            task_id=task_id or parent.task_id,
            execution_id=execution_id or parent.execution_id,
            evaluator_id=evaluator_id or parent.evaluator_id,
            attributes=attributes or {},
        )


# ---------------------------------------------------------------------------
# Attribute helpers
# ---------------------------------------------------------------------------


def truncate_text(value: str | None, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    limit = max_length or settings.otel_max_attribute_length
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated]"


def safe_json_attribute(value: object, max_length: int | None = None) -> str:
    try:
        serialized = json.dumps(value, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        serialized = str(value)
    return truncate_text(serialized, max_length=max_length) or ""


def normalize_attributes(attributes: dict[str, object] | None) -> dict[str, object]:
    if not attributes:
        return {}
    normalized: dict[str, object] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (bool, int, float)):
            normalized[key] = value
        elif isinstance(value, str):
            normalized[key] = truncate_text(value)
        else:
            normalized[key] = safe_json_attribute(value)
    return normalized


def datetime_to_nanos(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1_000_000_000)


# ---------------------------------------------------------------------------
# Deterministic ID helpers
# ---------------------------------------------------------------------------


def trace_id_from_run_id(run_id: UUID) -> int:
    """Derive a deterministic 128-bit trace ID from a run UUID."""
    return int(run_id.hex, 16) & _MAX_TRACE_ID


def span_id_from_key(*parts: str) -> int:
    """Derive a deterministic 64-bit span ID from arbitrary string parts."""
    digest = hashlib.sha256(":".join(parts).encode()).digest()[:8]
    return int.from_bytes(digest, "big") & _MAX_SPAN_ID or 1


class DeterministicIdGenerator:
    """OTEL ID generator that supports one-shot deterministic overrides."""

    def generate_trace_id(self) -> int:
        override = _desired_trace_id.get()
        if override is not None:
            return override
        return random.getrandbits(128)

    def generate_span_id(self) -> int:
        override = _desired_span_id.get()
        if override is not None:
            return override
        return random.getrandbits(64) or 1


@contextmanager
def _id_override(trace_id: int | None = None, span_id: int | None = None):
    trace_token = _desired_trace_id.set(trace_id) if trace_id is not None else None
    span_token = _desired_span_id.set(span_id) if span_id is not None else None
    try:
        yield
    finally:
        if span_token is not None:
            _desired_span_id.reset(span_token)
        if trace_token is not None:
            _desired_trace_id.reset(trace_token)


# ---------------------------------------------------------------------------
# OtelTraceSink
# ---------------------------------------------------------------------------


class OtelTraceSink:
    """OTEL-backed sink that exports spans via OTLP/gRPC."""

    def __init__(self) -> None:
        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name}),
            id_generator=DeterministicIdGenerator(),
        )
        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=settings.otel_exporter_otlp_insecure,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        otel_trace.set_tracer_provider(provider)

        self._provider: TracerProvider = provider
        self._tracer = otel_trace.get_tracer(settings.otel_service_name)

    def child_context(
        self,
        parent: TraceContext,
        *,
        span_key: str,
        run_id: UUID | None = None,
        task_id: UUID | None = None,
        execution_id: UUID | None = None,
        evaluator_id: UUID | None = None,
        attributes: dict[str, object] | None = None,
    ) -> TraceContext:
        return TraceContext(
            trace_id=parent.trace_id,
            span_id=span_id_from_key(str(parent.trace_id), str(parent.span_id), span_key),
            parent_span_id=parent.span_id,
            run_id=run_id if run_id is not None else parent.run_id,
            task_id=task_id if task_id is not None else parent.task_id,
            execution_id=execution_id if execution_id is not None else parent.execution_id,
            evaluator_id=evaluator_id if evaluator_id is not None else parent.evaluator_id,
            attributes=attributes or {},
        )

    def add_event(
        self,
        context: TraceContext,
        name: str,
        attributes: dict[str, object] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        now = timestamp or datetime.now(UTC)
        span = CompletedSpan(
            name=f"{name}.event",
            context=context,
            start_time=now,
            end_time=now,
            attributes=attributes or {},
            events=[SpanEvent(name=name, timestamp=now, attributes=attributes or {})],
        )
        self.emit_span(span)

    def emit_span(self, span: CompletedSpan) -> None:
        parent_ctx = None
        if span.context.parent_span_id not in (None, _EMPTY_SPAN_ID):
            span_context = SpanContext(
                trace_id=span.context.trace_id,
                span_id=span.context.parent_span_id,
                is_remote=False,
                trace_flags=TraceFlags(TRACE_FLAGS_SAMPLED),
                trace_state=TraceState(),
            )
            parent_ctx = set_span_in_context(NonRecordingSpan(span_context))

        start_time = datetime_to_nanos(span.start_time)
        end_time = datetime_to_nanos(span.end_time)
        attrs = normalize_attributes({**span.context.attributes, **span.attributes})

        with _id_override(
            trace_id=span.context.trace_id if span.context.parent_span_id is None else None,
            span_id=span.context.span_id,
        ):
            sdk_span = self._tracer.start_span(
                span.name,
                context=parent_ctx,
                attributes=attrs,
                start_time=start_time,
            )

        if str(span.status_code).lower() == "error":
            sdk_span.set_status(Status(StatusCode.ERROR, span.status_message))
        else:
            sdk_span.set_status(Status(StatusCode.OK))

        for event in span.events:
            sdk_span.add_event(
                event.name,
                attributes=normalize_attributes(event.attributes),
                timestamp=datetime_to_nanos(event.timestamp),
            )

        sdk_span.end(end_time=end_time)


# ---------------------------------------------------------------------------
# Process-wide sink
# ---------------------------------------------------------------------------


def _create_sink() -> TraceSink:
    if settings.otel_traces_enabled:
        try:
            return OtelTraceSink()
        except Exception:  # slopcop: ignore[no-broad-except]
            return NoopTraceSink()
    return NoopTraceSink()


_sink: TraceSink = _create_sink()


def get_trace_sink() -> TraceSink:
    """Return the process-wide trace sink.

    Each process (uvicorn worker, CLI invocation, test runner) gets its own
    sink created at import time. No locking needed — OTEL is stateless
    per-process and the collector handles fan-in from multiple exporters.
    """
    return _sink


# ---------------------------------------------------------------------------
# Context factories
# ---------------------------------------------------------------------------


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


def action_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    action_id: UUID,
) -> TraceContext:
    parent = worker_execute_context(run_id, task_id, execution_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key("action", str(run_id), str(action_id)),
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
