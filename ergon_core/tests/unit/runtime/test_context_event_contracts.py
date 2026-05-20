from uuid import uuid4

from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.views.runs.models import RunContextEventDto
from ergon_core.core.views.dashboard_events.context_events import (
    context_event_to_dashboard_event,
)
from ergon_core.core.views.dashboard_events.contracts import DashboardContextEventEvent
from ergon_core.core.shared.context_parts import AssistantTextPart, ContextPartChunkLog


def test_rest_and_dashboard_context_events_share_typed_payload_shape() -> None:
    payload = ContextPartChunkLog(
        part=AssistantTextPart(content="hello"),
        sequence=1,
        worker_binding_key="worker",
        turn_id="turn-1",
    )
    common = {
        "id": uuid4(),
        "run_id": uuid4(),
        "task_execution_id": uuid4(),
        "task_id": uuid4(),
        "worker_binding_key": "worker",
        "sequence": 1,
        "event_type": "assistant_text",
        "payload": payload,
        "created_at": "2026-04-28T00:00:00Z",
        "started_at": None,
        "completed_at": None,
    }

    rest = RunContextEventDto.model_validate(common)
    dashboard = DashboardContextEventEvent.model_validate(common)

    assert rest.payload == dashboard.payload
    assert rest.event_type == dashboard.event_type


def test_dashboard_context_event_serializes_canonical_task_id_field() -> None:
    event = DashboardContextEventEvent(
        id=uuid4(),
        run_id=uuid4(),
        task_execution_id=uuid4(),
        task_id=uuid4(),
        worker_binding_key="worker",
        sequence=1,
        event_type="assistant_text",
        payload=ContextPartChunkLog(
            part=AssistantTextPart(content="hello"),
            sequence=1,
            worker_binding_key="worker",
            turn_id="turn-1",
        ),
        created_at="2026-04-28T00:00:00Z",
        started_at=None,
        completed_at=None,
    )

    data = event.model_dump(mode="json")

    assert "task_id" in data
    assert "task_node_id" not in data


def test_context_event_row_mapper_uses_execution_task_map() -> None:
    run_id = uuid4()
    execution_id = uuid4()
    task_id = uuid4()
    payload = ContextPartChunkLog(
        part=AssistantTextPart(content="hello"),
        sequence=1,
        worker_binding_key="worker",
        turn_id="turn-1",
    )
    row = RunContextEvent(
        id=uuid4(),
        run_id=run_id,
        task_execution_id=execution_id,
        worker_binding_key="worker",
        sequence=1,
        event_type="assistant_text",
        payload=payload.model_dump(mode="json"),
        created_at="2026-04-28T00:00:00Z",
        started_at=None,
        completed_at=None,
    )

    event = context_event_to_dashboard_event(row, {execution_id: task_id})

    assert event == DashboardContextEventEvent(
        id=row.id,
        run_id=run_id,
        task_execution_id=execution_id,
        task_id=task_id,
        worker_binding_key="worker",
        sequence=1,
        event_type="assistant_text",
        payload=payload,
        created_at=row.created_at,
        started_at=None,
        completed_at=None,
    )


def test_context_event_row_mapper_returns_none_for_unknown_execution() -> None:
    row = RunContextEvent(
        id=uuid4(),
        run_id=uuid4(),
        task_execution_id=uuid4(),
        worker_binding_key="worker",
        sequence=1,
        event_type="assistant_text",
        payload=ContextPartChunkLog(
            part=AssistantTextPart(content="hello"),
            sequence=1,
            worker_binding_key="worker",
            turn_id="turn-1",
        ).model_dump(mode="json"),
        created_at="2026-04-28T00:00:00Z",
        started_at=None,
        completed_at=None,
    )

    assert context_event_to_dashboard_event(row, {}) is None
