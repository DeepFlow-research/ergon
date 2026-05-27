from datetime import UTC, datetime
from uuid import UUID, uuid4

from ergon_core.core.infrastructure.http.routes import samples as module
from ergon_core.core.infrastructure.http.routes.samples import router
from ergon_core.core.application.samples.events import SampleRuntimeEventView
from ergon_core.core.views.samples.models import SampleSummaryDto
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

    def list_events(self, sample_id: UUID) -> list[SampleRuntimeEventView] | None:
        self.calls.append({"sample_id": sample_id, "method": "list_events"})
        return [
            SampleRuntimeEventView(
                id=uuid4(),
                sample_id=sample_id,
                event_timestamp=datetime(2026, 5, 20, 12, 1, tzinfo=UTC),
                table="sample_task_events",
                event_type="task.status_changed",
                target_type="task",
                target_id=uuid4(),
                payload={"status": "completed"},
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


def test_sample_runtime_events_route_replaces_mutations_route(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    fake_service = _FakeSampleSnapshotReadService()
    sample_id = uuid4()

    monkeypatch.setattr(module, "SampleSnapshotReadService", lambda: fake_service)

    events_response = client.get(f"/samples/{sample_id}/events")
    mutations_response = client.get(f"/samples/{sample_id}/mutations")

    assert events_response.status_code == 200
    assert events_response.json()[0]["sample_id"] == str(sample_id)
    assert events_response.json()[0]["event_type"] == "task.status_changed"
    assert mutations_response.status_code in {404, 405}
