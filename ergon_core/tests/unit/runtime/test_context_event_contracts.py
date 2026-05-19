from uuid import uuid4

from ergon_core.core.application.read_models.models import RunContextEventDto
from ergon_core.core.infrastructure.dashboard.event_contracts import DashboardContextEventEvent
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
