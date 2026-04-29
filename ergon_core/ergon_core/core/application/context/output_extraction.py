"""Helpers for extracting worker outputs from persisted context events."""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.domain.generation.context_parts import AssistantTextPart
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.context.events import ContextEventService


def extract_assistant_text(events: Iterable[RunContextEvent]) -> str:
    """Return the last assistant text part from context events in iteration order."""
    text_events: list[str] = []
    for event in events:
        if event.event_type != "assistant_text":
            continue
        payload = event.parsed_payload()
        if isinstance(payload.part, AssistantTextPart):
            text_events.append(payload.part.content)
    return text_events[-1] if text_events else ""


def get_output(session: Any, execution_id: UUID) -> str:  # slopcop: ignore[no-typing-any]
    """Return assistant text output persisted for a worker execution."""
    events = ContextEventService().get_for_execution(session, execution_id)
    return extract_assistant_text(events)


def default_worker_output(context: WorkerContext) -> WorkerOutput:
    """Return the last assistant text persisted for a worker execution."""
    with get_session() as session:
        output = get_output(session, context.execution_id)

    return WorkerOutput(
        output=output,
        success=True,
    )
