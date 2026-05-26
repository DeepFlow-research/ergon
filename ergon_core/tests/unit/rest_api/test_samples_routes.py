from datetime import UTC, datetime
from uuid import UUID, uuid4

from ergon_core.core.infrastructure.http.routes import samples as module
from ergon_core.core.infrastructure.http.routes.samples import router
from ergon_core.core.views.samples.models import SampleSummaryDto
from ergon_core.core.views.samples.models import (
    SampleDetailView,
    SampleEventView,
    SampleEventsView,
    SampleGraphNodeView,
    SampleGraphView,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeSampleSnapshotReadService:
    calls: list[dict] = []

    def list_samples(
        self,
        *,
        limit: int = 20,
        status: str | None = None,
        definition_id: UUID | None = None,
        experiment: str | None = None,
        offset: int = 0,
    ) -> list[SampleSummaryDto]:
        self.calls.append(
            {
                "limit": limit,
                "status": status,
                "definition_id": definition_id,
                "experiment": experiment,
                "offset": offset,
            }
        )
        return [
            SampleSummaryDto(
                id=uuid4(),
                name="route sample",
                status="completed",
                created_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
                definition_id=definition_id or uuid4(),
                definition_name="route experiment",
                benchmark_type="route-bench",
                instance_key="sample-a",
                sample_label="sample-a",
                total_tasks=1,
                completed_tasks=1,
            )
        ]

def test_list_samples_route_passes_filters_to_read_service(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    fake_service = _FakeSampleSnapshotReadService()
    definition_id = uuid4()

    monkeypatch.setattr(module, "SampleSnapshotReadService", lambda: fake_service)

    response = client.get(
        f"/samples?limit=25&offset=50&status=completed&definition_id={definition_id}&experiment=alpha"
    )

    assert response.status_code == 200
    assert fake_service.calls == [
        {
            "limit": 25,
            "offset": 50,
            "status": "completed",
            "definition_id": definition_id,
            "experiment": "alpha",
        }
    ]
    body = response.json()
    assert body[0]["name"] == "route sample"
    assert body[0]["definition_name"] == "route experiment"
    assert body[0]["total_tasks"] == 1


class _FakeSampleReadService:
    def __init__(self) -> None:
        self.sample_id = uuid4()
        self.experiment_id = uuid4()
        self.environment_id = uuid4()
        self.task_id = uuid4()

    def get_sample_detail(self, sample_id: UUID):
        return SampleDetailView(
            sample_id=sample_id,
            experiment_id=self.experiment_id,
            environment_id=self.environment_id,
            environment_name="mini-validation",
            sample_key="problem-1",
            sample_ref={"id": "problem-1"},
            status="completed",
            created_at=datetime(2026, 5, 26, tzinfo=UTC),
        )

    def list_sample_events(self, sample_id: UUID):
        return SampleEventsView(
            items=[
                SampleEventView(
                    event_id=uuid4(),
                    sample_id=sample_id,
                    event_type="task.added",
                    target_type="task",
                    target_id=self.task_id,
                    timestamp=datetime(2026, 5, 26, tzinfo=UTC),
                )
            ]
        )

    def get_sample_graph(self, sample_id: UUID):
        return SampleGraphView(
            nodes=[
                SampleGraphNodeView(
                    task_id=self.task_id,
                    task_slug="solve",
                    description="Solve problem 1",
                    status="completed",
                    created_at=datetime(2026, 5, 26, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 26, tzinfo=UTC),
                )
            ]
        )


def test_sample_detail_events_and_graph_routes(monkeypatch) -> None:
    service = _FakeSampleReadService()
    monkeypatch.setattr(module, "SampleReadService", lambda: service)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    detail = client.get(f"/samples/{service.sample_id}")
    events = client.get(f"/samples/{service.sample_id}/events")
    graph = client.get(f"/samples/{service.sample_id}/graph")

    assert detail.status_code == 200
    assert detail.json()["sampleId"] == str(service.sample_id)
    assert detail.json()["experimentId"] == str(service.experiment_id)
    assert "runId" not in detail.text
    assert events.status_code == 200
    assert events.json()["items"][0]["eventType"] == "task.added"
    assert "GraphMutation" not in events.text
    assert graph.status_code == 200
    assert graph.json()["nodes"][0]["taskSlug"] == "solve"


def test_sample_mutations_route_is_removed(monkeypatch) -> None:
    service = _FakeSampleReadService()
    monkeypatch.setattr(module, "SampleReadService", lambda: service)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get(f"/samples/{service.sample_id}/mutations")

    assert response.status_code in {404, 405}
