"""No-op tracing sink."""

from datetime import datetime
from uuid import UUID

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.infrastructure.tracing.ids import span_id_from_key
from ergon_core.core.infrastructure.tracing.types import CompletedSpan, TraceContext


class NoopTraceSink:
    """Default sink that discards everything."""

    def emit_span(self, span: CompletedSpan) -> None:
        pass

    def add_event(
        self,
        context: TraceContext,
        name: str,
        attributes: JsonObject | None = None,
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
        attributes: JsonObject | None = None,
    ) -> TraceContext:
        child_span = span_id_from_key(str(parent.span_id), span_key)
        return TraceContext(
            trace_id=parent.trace_id,
            span_id=child_span,
            parent_span_id=parent.span_id,
            run_id=parent.run_id if run_id is None else run_id,
            task_id=parent.task_id if task_id is None else task_id,
            execution_id=parent.execution_id if execution_id is None else execution_id,
            evaluator_id=parent.evaluator_id if evaluator_id is None else evaluator_id,
            attributes={} if attributes is None else attributes,
        )
