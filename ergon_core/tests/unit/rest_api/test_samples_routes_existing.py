from datetime import UTC, datetime
from uuid import UUID, uuid4

from ergon_core.core.infrastructure.http.routes import samples as module
from ergon_core.core.infrastructure.http.routes.samples import router
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
        experiment: str | None = None,
        offset: int = 0,
    ) -> list[SampleSummaryDto]:
        self.calls.append(
            {
                "limit": limit,
                "status": status,
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
                experiment_id=uuid4(),
                experiment=experiment,
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

    monkeypatch.setattr(module, "SampleSnapshotReadService", lambda: fake_service)

    response = client.get("/samples?limit=25&offset=50&status=completed&experiment=alpha")

    assert response.status_code == 200
    assert fake_service.calls == [
        {
            "limit": 25,
            "offset": 50,
            "status": "completed",
            "experiment": "alpha",
        }
    ]
    body = response.json()
    assert body[0]["name"] == "route sample"
    assert body[0]["experiment"] == "alpha"
    assert body[0]["total_tasks"] == 1
