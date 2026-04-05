"""OTEL tracing helpers and sink implementations."""

from __future__ import annotations

import hashlib
import json
import random
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID

from h_arcane.core.settings import settings

TRACE_FLAGS_SAMPLED = 0x01
_MAX_TRACE_ID = (1 << 128) - 1
_MAX_SPAN_ID = (1 << 64) - 1
_EMPTY_SPAN_ID = 0

_desired_trace_id: ContextVar[int | None] = ContextVar("desired_trace_id", default=None)
_desired_span_id: ContextVar[int | None] = ContextVar("desired_span_id", default=None)
_trace_sink_override: ContextVar["TraceSink | None"] = ContextVar(
    "trace_sink_override",
    default=None,
)

_trace_sink_lock = Lock()
_trace_sink_singleton: "TraceSink | None" = None


def _hash_parts(*parts: object) -> bytes:
    joined = "||".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).digest()


def trace_id_from_run_id(run_id: UUID) -> int:
    """Derive a deterministic OTEL trace ID from a run UUID."""
    return int(run_id.hex, 16) & _MAX_TRACE_ID


def span_id_from_key(*parts: object) -> int:
    """Derive a deterministic non-zero OTEL span ID from semantic parts."""
    span_id = int.from_bytes(_hash_parts(*parts)[:8], byteorder="big") & _MAX_SPAN_ID
    return span_id or 1


def truncate_text(value: str | None, max_length: int | None = None) -> str | None:
    """Truncate text payloads to avoid huge OTEL attributes."""
    if value is None:
        return None
    limit = max_length or getattr(settings, "otel_max_attribute_length", 4000)
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated]"


def safe_json_attribute(value: Any, max_length: int | None = None) -> str:
    """Serialize arbitrary values into a bounded OTEL attribute string."""
    try:
        serialized = json.dumps(value, default=str, separators=(",", ":"))
    except Exception:
        serialized = str(value)
    return truncate_text(serialized, max_length=max_length) or ""


def normalize_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize attributes to OTEL-safe scalar values."""
    if not attributes:
        return {}

    normalized: dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (bool, int, float)):
            normalized[key] = value
            continue
        if isinstance(value, str):
            normalized[key] = truncate_text(value)
            continue
        normalized[key] = safe_json_attribute(value)
    return normalized


def datetime_to_otel_nanos(value: datetime) -> int:
    """Convert datetimes to OTEL's integer nanosecond timestamps."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1_000_000_000)


@dataclass(frozen=True)
class TraceContext:
    """Deterministic tracing identity for a logical span."""

    trace_id: int
    span_id: int
    parent_span_id: int | None = None
    run_id: UUID | None = None
    task_id: UUID | None = None
    execution_id: UUID | None = None
    evaluator_id: UUID | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpanEvent:
    """Structured event attached to a span."""

    name: str
    timestamp: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompletedSpan:
    """Fully-formed span data ready for export."""

    name: str
    context: TraceContext
    start_time: datetime
    end_time: datetime
    attributes: dict[str, Any] = field(default_factory=dict)
    status_code: str = "ok"
    status_message: str | None = None
    events: tuple[SpanEvent, ...] = ()


class TraceSink(Protocol):
    """Framework-agnostic tracing sink."""

    def emit_span(self, span: CompletedSpan) -> None: ...

    def add_event(
        self,
        context: TraceContext,
        name: str,
        attributes: dict[str, Any] | None = None,
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
        attributes: dict[str, Any] | None = None,
    ) -> TraceContext: ...


class NoopTraceSink:
    """Disabled tracing implementation."""

    def emit_span(self, span: CompletedSpan) -> None:
        return None

    def add_event(
        self,
        context: TraceContext,
        name: str,
        attributes: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        return None

    def child_context(
        self,
        parent: TraceContext,
        *,
        span_key: str,
        run_id: UUID | None = None,
        task_id: UUID | None = None,
        execution_id: UUID | None = None,
        evaluator_id: UUID | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> TraceContext:
        return TraceContext(
            trace_id=parent.trace_id,
            span_id=span_id_from_key(parent.trace_id, span_key),
            parent_span_id=parent.span_id,
            run_id=run_id if run_id is not None else parent.run_id,
            task_id=task_id if task_id is not None else parent.task_id,
            execution_id=execution_id if execution_id is not None else parent.execution_id,
            evaluator_id=evaluator_id if evaluator_id is not None else parent.evaluator_id,
            attributes=attributes or {},
        )


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


class OtelTraceSink:
    """OTEL-backed sink that exports spans through OTLP."""

    def __init__(self) -> None:
        self._provider: Any | None = None
        self._tracer = None
        self._init_lock = Lock()

    def child_context(
        self,
        parent: TraceContext,
        *,
        span_key: str,
        run_id: UUID | None = None,
        task_id: UUID | None = None,
        execution_id: UUID | None = None,
        evaluator_id: UUID | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> TraceContext:
        return TraceContext(
            trace_id=parent.trace_id,
            span_id=span_id_from_key(parent.trace_id, parent.span_id, span_key),
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
        attributes: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        now = timestamp or datetime.now(UTC)
        span = CompletedSpan(
            name=f"{name}.event",
            context=context,
            start_time=now,
            end_time=now,
            attributes=attributes or {},
            events=(SpanEvent(name=name, timestamp=now, attributes=attributes or {}),),
        )
        self.emit_span(span)

    def emit_span(self, span: CompletedSpan) -> None:
        tracer = self._get_tracer()
        if tracer is None:
            return

        imports = _otel_imports()
        parent_context = self._parent_context(span.context.parent_span_id, span.context.trace_id, imports)
        start_time = datetime_to_otel_nanos(span.start_time)
        end_time = datetime_to_otel_nanos(span.end_time)
        attributes = normalize_attributes({**span.context.attributes, **span.attributes})

        with _id_override(
            trace_id=span.context.trace_id if span.context.parent_span_id is None else None,
            span_id=span.context.span_id,
        ):
            sdk_span = tracer.start_span(
                span.name,
                context=parent_context,
                attributes=attributes,
                start_time=start_time,
            )

        if span.status_code.lower() == "error":
            sdk_span.set_status(imports["Status"](imports["StatusCode"].ERROR, span.status_message))
        else:
            sdk_span.set_status(imports["Status"](imports["StatusCode"].OK))

        for event in span.events:
            sdk_span.add_event(
                event.name,
                attributes=normalize_attributes(event.attributes),
                timestamp=datetime_to_otel_nanos(event.timestamp or span.end_time),
            )

        sdk_span.end(end_time=end_time)

    def _get_tracer(self):
        if self._tracer is not None:
            return self._tracer

        with self._init_lock:
            if self._tracer is not None:
                return self._tracer
            try:
                imports = _otel_imports()
            except Exception:
                return None

            provider = imports["TracerProvider"](
                resource=imports["Resource"].create(
                    {"service.name": getattr(settings, "otel_service_name", "h-arcane")}
                ),
                id_generator=DeterministicIdGenerator(),
            )
            exporter = imports["OTLPSpanExporter"](
                endpoint=getattr(settings, "otel_exporter_otlp_endpoint", "http://localhost:4317"),
                insecure=getattr(settings, "otel_exporter_otlp_insecure", True),
            )
            provider.add_span_processor(imports["BatchSpanProcessor"](exporter))
            imports["trace"].set_tracer_provider(provider)
            self._provider = provider
            self._tracer = imports["trace"].get_tracer(
                getattr(settings, "otel_service_name", "h-arcane")
            )
            return self._tracer

    def _parent_context(self, parent_span_id: int | None, trace_id: int, imports: dict[str, Any]):
        if parent_span_id in (None, _EMPTY_SPAN_ID):
            return None
        span_context = imports["SpanContext"](
            trace_id=trace_id,
            span_id=parent_span_id,
            is_remote=False,
            trace_flags=imports["TraceFlags"](TRACE_FLAGS_SAMPLED),
            trace_state=imports["TraceState"](),
        )
        return imports["set_span_in_context"](imports["NonRecordingSpan"](span_context))


def get_trace_sink() -> TraceSink:
    """Get the process-wide tracing sink."""
    global _trace_sink_singleton

    override = _trace_sink_override.get()
    if override is not None:
        return override

    if _trace_sink_singleton is not None:
        return _trace_sink_singleton

    with _trace_sink_lock:
        if _trace_sink_singleton is not None:
            return _trace_sink_singleton
        if not getattr(settings, "otel_traces_enabled", False):
            _trace_sink_singleton = NoopTraceSink()
        else:
            try:
                _trace_sink_singleton = OtelTraceSink()
            except Exception:
                _trace_sink_singleton = NoopTraceSink()
        return _trace_sink_singleton


@contextmanager
def override_trace_sink(trace_sink: TraceSink):
    """Temporarily override the active trace sink for the current context."""
    token = _trace_sink_override.set(trace_sink)
    try:
        yield trace_sink
    finally:
        _trace_sink_override.reset(token)


def workflow_root_context(run_id: UUID, attributes: dict[str, Any] | None = None) -> TraceContext:
    return TraceContext(
        trace_id=trace_id_from_run_id(run_id),
        span_id=span_id_from_key(run_id, "workflow.execute"),
        parent_span_id=None,
        run_id=run_id,
        attributes=attributes or {},
    )


def workflow_start_context(run_id: UUID, attributes: dict[str, Any] | None = None) -> TraceContext:
    root = workflow_root_context(run_id)
    return TraceContext(
        trace_id=root.trace_id,
        span_id=span_id_from_key(run_id, "workflow.start"),
        parent_span_id=root.span_id,
        run_id=run_id,
        attributes=attributes or {},
    )


def workflow_terminal_context(
    run_id: UUID, phase: str, attributes: dict[str, Any] | None = None
) -> TraceContext:
    root = workflow_root_context(run_id)
    return TraceContext(
        trace_id=root.trace_id,
        span_id=span_id_from_key(run_id, f"workflow.{phase}"),
        parent_span_id=root.span_id,
        run_id=run_id,
        attributes=attributes or {},
    )


def task_execute_context(
    run_id: UUID,
    task_id: UUID,
    attempt_number: int = 1,
    execution_id: UUID | None = None,
    attributes: dict[str, Any] | None = None,
) -> TraceContext:
    root = workflow_root_context(run_id)
    return TraceContext(
        trace_id=root.trace_id,
        span_id=span_id_from_key(run_id, task_id, attempt_number, "task.execute"),
        parent_span_id=root.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        attributes=attributes or {},
    )


def sandbox_setup_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID | None = None,
    attributes: dict[str, Any] | None = None,
) -> TraceContext:
    parent = task_execute_context(run_id, task_id, execution_id=execution_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(run_id, task_id, execution_id or "none", "sandbox.setup"),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        attributes=attributes or {},
    )


def sandbox_file_op_context(
    run_id: UUID,
    task_id: UUID,
    operation: str,
    execution_id: UUID | None = None,
    index: int | None = None,
    attributes: dict[str, Any] | None = None,
) -> TraceContext:
    parent = task_execute_context(run_id, task_id, execution_id=execution_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(run_id, task_id, execution_id or "none", operation, index or 0),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        attributes=attributes or {},
    )


def worker_execute_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    attributes: dict[str, Any] | None = None,
) -> TraceContext:
    parent = task_execute_context(run_id, task_id, execution_id=execution_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(run_id, task_id, execution_id, "worker.execute"),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        attributes=attributes or {},
    )


def tool_action_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    action_id: UUID,
    attributes: dict[str, Any] | None = None,
) -> TraceContext:
    parent = worker_execute_context(run_id, task_id, execution_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(run_id, action_id, "tool"),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        attributes=attributes or {},
    )


def persist_outputs_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    attributes: dict[str, Any] | None = None,
) -> TraceContext:
    parent = task_execute_context(run_id, task_id, execution_id=execution_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(run_id, task_id, execution_id, "persist.outputs"),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        attributes=attributes or {},
    )


def evaluation_task_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    evaluator_id: UUID,
    attributes: dict[str, Any] | None = None,
) -> TraceContext:
    parent = task_execute_context(run_id, task_id, execution_id=execution_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(run_id, task_id, execution_id, evaluator_id, "evaluation.task"),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        evaluator_id=evaluator_id,
        attributes=attributes or {},
    )


def evaluation_criterion_context(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    evaluator_id: UUID,
    stage_idx: int,
    criterion_idx: int,
    attributes: dict[str, Any] | None = None,
) -> TraceContext:
    parent = evaluation_task_context(run_id, task_id, execution_id, evaluator_id)
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=span_id_from_key(
            run_id,
            task_id,
            execution_id,
            evaluator_id,
            stage_idx,
            criterion_idx,
            "evaluation.criterion",
        ),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        evaluator_id=evaluator_id,
        attributes=attributes or {},
    )


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


def _otel_imports() -> dict[str, Any]:
    from opentelemetry import trace  # type: ignore[import-not-found]
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-not-found]
    from opentelemetry.trace import (  # type: ignore[import-not-found]
        NonRecordingSpan,
        SpanContext,
        Status,
        StatusCode,
        TraceFlags,
    )
    from opentelemetry.trace.propagation import set_span_in_context  # type: ignore[import-not-found]
    from opentelemetry.trace.span import TraceState  # type: ignore[import-not-found]

    return {
        "trace": trace,
        "OTLPSpanExporter": OTLPSpanExporter,
        "Resource": Resource,
        "TracerProvider": TracerProvider,
        "BatchSpanProcessor": BatchSpanProcessor,
        "NonRecordingSpan": NonRecordingSpan,
        "SpanContext": SpanContext,
        "Status": Status,
        "StatusCode": StatusCode,
        "TraceFlags": TraceFlags,
        "TraceState": TraceState,
        "set_span_in_context": set_span_in_context,
    }
