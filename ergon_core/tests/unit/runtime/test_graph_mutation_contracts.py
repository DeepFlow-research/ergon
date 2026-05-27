from uuid import uuid4

from ergon_core.core.application.samples.event_views import sample_runtime_event_from_row
from ergon_core.core.persistence.samples.models import SampleEdgeEventRow
from ergon_core.core.views.dashboard_events.contracts import DashboardSampleRuntimeEvent


def test_rest_and_dashboard_events_share_typed_sample_wal_payloads() -> None:
    sample_id = uuid4()
    edge_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()
    row = SampleEdgeEventRow(
        sample_id=sample_id,
        edge_id=edge_id,
        source_task_id=source_id,
        target_task_id=target_id,
        event_type="edge.added",
        status="pending",
        payload_json={"status": "pending"},
    )

    dto = sample_runtime_event_from_row(row)
    event = DashboardSampleRuntimeEvent(event=dto)

    assert event.event.event_type == "edge.added"
    assert event.event.target_id == edge_id
    assert event.event.source_task_id == source_id
    assert event.event.target_task_id == target_id
    data = event.model_dump(mode="json")
    assert data["event"]["source_task_id"] == str(source_id)
    assert data["event"]["target_task_id"] == str(target_id)
