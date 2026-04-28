"""Tracing data contracts."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from ergon_core.core.json_types import JsonObject


class TraceContext(BaseModel):
    model_config = {"frozen": True}

    trace_id: int
    span_id: int
    parent_span_id: int | None = None
    run_id: UUID | None = None
    task_id: UUID | None = None
    execution_id: UUID | None = None
    evaluator_id: UUID | None = None
    attributes: JsonObject = Field(default_factory=dict)


class SpanEvent(BaseModel):
    model_config = {"frozen": True}

    name: str
    timestamp: datetime
    attributes: JsonObject = Field(default_factory=dict)


class CompletedSpan(BaseModel):
    model_config = {"frozen": True}

    name: str
    context: TraceContext
    start_time: datetime
    end_time: datetime
    attributes: JsonObject = Field(default_factory=dict)
    status_code: int | str = 0
    status_message: str | None = None
    events: list[SpanEvent] = Field(default_factory=list)


class TraceSink(Protocol):
    def emit_span(self, span: CompletedSpan) -> None: ...

    def add_event(
        self,
        context: TraceContext,
        name: str,
        attributes: JsonObject | None = None,
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
        attributes: JsonObject | None = None,
    ) -> TraceContext: ...
