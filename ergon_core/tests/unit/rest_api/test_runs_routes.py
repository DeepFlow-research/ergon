from datetime import UTC, datetime
from uuid import UUID, uuid4

from ergon_core.core.infrastructure.http.routes import runs as module
from ergon_core.core.infrastructure.http.routes.runs import router
from ergon_core.core.views.runs.models import RunSummaryDto
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeRunReadService:
    calls: list[dict] = []

    def list_runs(
        self,
        *,
        limit: int = 20,
        status: str | None = None,
        definition_id: UUID | None = None,
        experiment: str | None = None,
        offset: int = 0,
    ) -> list[RunSummaryDto]:
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
            RunSummaryDto(
                id=uuid4(),
                name="route run",
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


def test_list_runs_route_passes_filters_to_read_service(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    fake_service = _FakeRunReadService()
    definition_id = uuid4()

    monkeypatch.setattr(module, "RunReadService", lambda: fake_service)

    response = client.get(
        f"/runs?limit=25&offset=50&status=completed&definition_id={definition_id}&experiment=alpha"
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
    assert body[0]["name"] == "route run"
    assert body[0]["definition_name"] == "route experiment"
    assert body[0]["total_tasks"] == 1
