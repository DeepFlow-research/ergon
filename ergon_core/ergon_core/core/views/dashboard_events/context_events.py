"""Dashboard event projections for persisted context event rows."""

from typing import cast
from uuid import UUID

from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.shared.context_parts import ContextEventType
from ergon_core.core.views.dashboard_events.contracts import DashboardContextEventEvent


def context_event_to_dashboard_event(
    event: SampleContextEvent,
    execution_task_map: dict[UUID, UUID],
) -> DashboardContextEventEvent | None:
    task_id = execution_task_map.get(event.task_attempt_id)
    if task_id is None:
        return None
    return DashboardContextEventEvent(
        id=event.id,
        sample_id=event.sample_id,
        task_attempt_id=event.task_attempt_id,
        task_id=task_id,
        worker_binding_key=event.worker_binding_key,
        sequence=event.sequence,
        event_type=cast(ContextEventType, event.event_type),
        payload=event.parsed_payload(),
        created_at=event.created_at,
        started_at=event.started_at,
        completed_at=event.completed_at,
    )
