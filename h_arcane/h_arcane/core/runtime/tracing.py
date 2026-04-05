"""OTEL-compatible tracing facade.

Provides a lightweight tracing abstraction with a NoopTraceSink default.
When settings.otel_traces_enabled is True, OtelTraceSink exports spans via OTLP.
"""

from __future__ import annotations

import hashlib
import json
import random
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID

from h_arcane.core.settings import settings
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
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanEvent(BaseModel):
    model_config = {"frozen": True}

    name: str
    timestamp: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)


class CompletedSpan(BaseModel):
    model_config = {"frozen": True}

    name: str
    context: TraceContext
    start_time: datetime
    end_time: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)
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
    """Default sink that discards everything. Zero overhead."""

    def emit_span(self, span: CompletedSpan) -> None:
        pass

    def add_event(
        self,
        context: TraceContext,
        name: str,
        attributes: dict[str, Any] | None = None,
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
        attributes: dict[str, Any] | None = None,
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
# OTEL attribute helpers
# ---------------------------------------------------------------------------


def truncate_text(value: str | None, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    limit = max_length or settings.otel_max_attribute_length
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated]"


def safe_json_attribute(value: Any, max_length: int | None = None) -> str:
    try:
        serialized = json.dumps(value, default=str, separators=(",", ":"))
    except Exception:
        serialized = str(value)
    return truncate_text(serialized, max_length=max_length) or ""


def normalize_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    if not attributes:
        return {}
    normalized: dict[str, Any] = {}
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


def datetime_to_otel_nanos(value: datetime) -> int:
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


# ---------------------------------------------------------------------------
# OtelTraceSink
# ---------------------------------------------------------------------------


class OtelTraceSink:
    """OTEL-backed sink that exports spans via OTLP/gRPC."""

    def __init__(self) -> None:
        self._provider: Any | None = None
        self._tracer: Any | None = None
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
            events=[SpanEvent(name=name, timestamp=now, attributes=attributes or {})],
        )
        self.emit_span(span)

    def emit_span(self, span: CompletedSpan) -> None:
        tracer = self._get_tracer()
        if tracer is None:
            return

        imports = _otel_imports()
        parent_context = self._parent_context(
            span.context.parent_span_id, span.context.trace_id, imports,
        )
        start_time = datetime_to_otel_nanos(span.start_time)
        end_time = datetime_to_otel_nanos(span.end_time)
        attrs = normalize_attributes({**span.context.attributes, **span.attributes})

        with _id_override(
            trace_id=span.context.trace_id if span.context.parent_span_id is None else None,
            span_id=span.context.span_id,
        ):
            sdk_span = tracer.start_span(
                span.name,
                context=parent_context,
                attributes=attrs,
                start_time=start_time,
            )

        if str(span.status_code).lower() == "error":
            sdk_span.set_status(
                imports["Status"](imports["StatusCode"].ERROR, span.status_message),
            )
        else:
            sdk_span.set_status(imports["Status"](imports["StatusCode"].OK))

        for event in span.events:
            sdk_span.add_event(
                event.name,
                attributes=normalize_attributes(event.attributes),
                timestamp=datetime_to_otel_nanos(event.timestamp),
            )

        sdk_span.end(end_time=end_time)

    # ------------------------------------------------------------------

    def _get_tracer(self) -> Any | None:
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
                    {"service.name": settings.otel_service_name}
                ),
                id_generator=DeterministicIdGenerator(),
            )
            exporter = imports["OTLPSpanExporter"](
                endpoint=settings.otel_exporter_otlp_endpoint,
                insecure=settings.otel_exporter_otlp_insecure,
            )
            provider.add_span_processor(imports["BatchSpanProcessor"](exporter))
            imports["trace"].set_tracer_provider(provider)
            self._provider = provider
            self._tracer = imports["trace"].get_tracer(settings.otel_service_name)
            return self._tracer

    @staticmethod
    def _parent_context(
        parent_span_id: int | None,
        trace_id: int,
        imports: dict[str, Any],
    ) -> Any | None:
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


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_sink_lock = Lock()
_sink: TraceSink | None = None


def get_trace_sink() -> TraceSink:
    """Return the process-wide trace sink (lazy-initialised)."""
    global _sink  # noqa: PLW0603

    if _sink is not None:
        return _sink

    with _sink_lock:
        if _sink is not None:
            return _sink
        if settings.otel_traces_enabled:
            try:
                _sink = OtelTraceSink()
            except Exception:
                _sink = NoopTraceSink()
        else:
            _sink = NoopTraceSink()
        return _sink


# ---------------------------------------------------------------------------
# OTEL import helper (deferred so packages remain optional)
# ---------------------------------------------------------------------------


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
    from opentelemetry.trace.propagation import (
        set_span_in_context,  # type: ignore[import-not-found]
    )
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
            "evaluation_task", str(run_id), str(task_id),
            str(execution_id), str(evaluator_id),
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
            "evaluation_criterion", str(run_id), str(task_id),
            str(execution_id), str(evaluator_id),
            str(stage_idx), str(criterion_idx),
        ),
        parent_span_id=parent.span_id,
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        evaluator_id=evaluator_id,
    )
