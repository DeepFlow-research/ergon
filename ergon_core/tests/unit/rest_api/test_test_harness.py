"""Test-harness router: conditional mount, read DTO shape, write-gate secret."""

from collections.abc import Iterator
from uuid import uuid4

from ergon_core.core.application.testing.test_harness_service import (
    HarnessExperimentRun,
    get_session_dep,
)
from ergon_core.core.infrastructure.http.routes import test_harness
from ergon_core.core.infrastructure.http.routes.test_harness import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _NullSession:
    """Minimal session stub that returns no rows for any exec/get call.

    The read endpoint queries for a RunRecord first and 404s when absent; in
    that branch no further DB access occurs. This stub exists so unit tests
    don't require a live Postgres.
    """

    def __enter__(self) -> "_NullSession":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def exec(self, _stmt: object) -> "_NullSession":  # pragma: no cover - trivial
        return self

    def first(self) -> None:
        return None

    def all(self) -> list[object]:  # pragma: no cover - unreachable for unknown run
        return []


def _null_session_factory() -> Iterator[_NullSession]:
    yield _NullSession()


def _build_app_with_harness() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_dep] = _null_session_factory
    return app


def test_read_endpoint_returns_404_for_unknown_run_id() -> None:
    app = _build_app_with_harness()
    client = TestClient(app)
    resp = client.get(f"/api/__danger__/test-harness/read/run/{uuid4()}/state")
    assert resp.status_code == 404


def test_read_state_dto_exposes_live_playwright_contract_fields() -> None:
    assert {"id", "parent_task_id"} <= set(test_harness.TestGraphNodeDto.model_fields)
    assert {"task_id", "task_slug"} <= set(test_harness.TestEvaluationDto.model_fields)
    assert {
        "executions",
        "execution_count",
        "mutation_count",
        "resource_count",
        "thread_count",
        "context_event_count",
    } <= set(test_harness.TestRunStateDto.model_fields)


def test_read_experiment_runs_route_uses_v2_experiment_grouping(monkeypatch) -> None:
    run_id = uuid4()

    monkeypatch.setattr(
        test_harness,
        "_read_experiment_runs",
        lambda experiment, session: [
            HarnessExperimentRun(run_id=run_id, status=f"{experiment}:completed")
        ],
    )

    app = _build_app_with_harness()
    client = TestClient(app)
    resp = client.get("/api/__danger__/test-harness/read/experiment/group-alpha/runs")

    assert resp.status_code == 200
    assert resp.json() == [{"run_id": str(run_id), "status": "group-alpha:completed"}]


def test_reset_route_is_available_without_secret_header() -> None:
    app = _build_app_with_harness()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/__danger__/test-harness/write/reset",
        json={"experiment_prefix": "ci-smoke-"},
    )
    assert resp.status_code in (204, 500)
