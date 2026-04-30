"""OpenTelemetry tracing sink."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    Status,
    StatusCode,
    TraceFlags,
)
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.trace.span import TraceState

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as _OTLPSpanExporter,
    )
except ImportError:
    _OTLPSpanExporter = None

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.infrastructure.tracing.attributes import (
    datetime_to_nanos,
    normalize_attributes,
)
from ergon_core.core.infrastructure.tracing.ids import (
    EMPTY_SPAN_ID,
    TRACE_FLAGS_SAMPLED,
    DeterministicIdGenerator,
    id_override,
    span_id_from_key,
)
from ergon_core.core.infrastructure.tracing.types import CompletedSpan, SpanEvent, TraceContext
from ergon_core.core.shared.settings import settings


class OtelTraceSink:
    """OTEL-backed sink that exports spans via OTLP/gRPC."""

    def __init__(self) -> None:
        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name}),
            id_generator=cast(Any, DeterministicIdGenerator()),
        )
        if _OTLPSpanExporter is None:
            raise RuntimeError("opentelemetry OTLP exporter is not installed")
        exporter = _OTLPSpanExporter(
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
        attributes: JsonObject | None = None,
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
        attributes: JsonObject | None = None,
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
        if span.context.parent_span_id not in (None, EMPTY_SPAN_ID):
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

        with id_override(
            trace_id=span.context.trace_id if span.context.parent_span_id is None else None,
            span_id=span.context.span_id,
        ):
            sdk_span = self._tracer.start_span(
                span.name,
                context=parent_ctx,
                attributes=cast(Any, attrs),
                start_time=start_time,
            )

        if str(span.status_code).lower() == "error":
            sdk_span.set_status(Status(StatusCode.ERROR, span.status_message))
        else:
            sdk_span.set_status(Status(StatusCode.OK))

        for event in span.events:
            sdk_span.add_event(
                event.name,
                attributes=cast(Any, normalize_attributes(event.attributes)),
                timestamp=datetime_to_nanos(event.timestamp),
            )

        sdk_span.end(end_time=end_time)
