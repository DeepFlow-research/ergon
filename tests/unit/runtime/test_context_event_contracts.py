from uuid import uuid4

from ergon_core.core.api.schemas import RunContextEventDto
from ergon_core.core.dashboard.event_contracts import DashboardContextEventEvent
from ergon_core.core.generation import AssistantTextPart, ContextPartChunkLog


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
        "task_node_id": uuid4(),
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
