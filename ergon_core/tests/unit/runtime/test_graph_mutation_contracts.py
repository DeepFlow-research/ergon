from uuid import uuid4

from ergon_core.core.application.graph.models import (
    EdgeAddedMutation,
    GraphMutationRecordDto,
    GraphMutationValue,
)
from ergon_core.core.persistence.graph.models import RunGraphMutation
from ergon_core.core.views.dashboard_events.contracts import DashboardGraphMutationEvent
from ergon_core.core.views.dashboard_events.graph_mutations import (
    dashboard_graph_mutation_event_from_row,
    graph_mutation_record_from_row,
)
from pydantic import TypeAdapter


def test_rest_and_dashboard_mutations_share_graph_mutation_record_payloads() -> None:
    run_id = uuid4()
    mutation_id = uuid4()
    edge_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()

    payload = EdgeAddedMutation(
        source_task_id=source_id,
        target_task_id=target_id,
        status="pending",
    )

    TypeAdapter(GraphMutationValue).validate_python(payload.model_dump(mode="json"))

    record = GraphMutationRecordDto(
        id=mutation_id,
        run_id=run_id,
        sequence=1,
        mutation_type="edge.added",
        target_type="edge",
        target_id=edge_id,
        actor="test",
        old_value=None,
        new_value=payload,
        reason=None,
        created_at="2026-04-28T00:00:00Z",
    )
    dashboard = DashboardGraphMutationEvent(
        mutation=record,
    )

    assert dashboard.mutation == record
    assert record.new_value == payload

    data = dashboard.model_dump(mode="json")
    edge_value = data["mutation"]["new_value"]
    assert edge_value["source_task_id"] == str(source_id)
    assert edge_value["target_task_id"] == str(target_id)
    assert "source_node_id" not in edge_value
    assert "target_node_id" not in edge_value


def test_graph_mutation_row_mapper_is_shared_by_rest_and_dashboard_events() -> None:
    run_id = uuid4()
    mutation_id = uuid4()
    edge_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()
    row = RunGraphMutation(
        id=mutation_id,
        run_id=run_id,
        sequence=7,
        mutation_type="edge.added",
        target_type="edge",
        target_id=edge_id,
        actor="manager",
        old_value=None,
        new_value={
            "mutation_type": "edge.added",
            "source_task_id": str(source_id),
            "target_task_id": str(target_id),
            "status": "pending",
        },
        reason="spawn dependency",
        created_at="2026-04-28T00:00:00Z",
    )

    record = graph_mutation_record_from_row(row)
    event = dashboard_graph_mutation_event_from_row(row)

    assert event == DashboardGraphMutationEvent(mutation=record)
    assert record.id == mutation_id
    assert record.run_id == run_id
    assert record.new_value == EdgeAddedMutation(
        source_task_id=source_id,
        target_task_id=target_id,
        status="pending",
    )
