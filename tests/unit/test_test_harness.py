"""Test-harness router: conditional mount, read DTO shape, write-gate secret."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ergon_core.core.api import test_harness
from ergon_core.core.api.startup_plugins import run_startup_plugins
from ergon_core.core.api.test_harness import get_session_dep, router


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


def _build_app_with_harness(
    monkeypatch: pytest.MonkeyPatch, *, enabled: bool, secret: str | None = "ci-secret"
) -> FastAPI:
    app = FastAPI()
    monkeypatch.setenv("ENABLE_TEST_HARNESS", "1" if enabled else "0")
    if secret is not None:
        monkeypatch.setenv("TEST_HARNESS_SECRET", secret)
    else:
        monkeypatch.delenv("TEST_HARNESS_SECRET", raising=False)

    if enabled:
        app.include_router(router)
        app.dependency_overrides[get_session_dep] = _null_session_factory
    return app


def test_read_endpoint_returns_404_for_unknown_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app_with_harness(monkeypatch, enabled=True)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404


def test_read_state_dto_exposes_live_playwright_contract_fields() -> None:
    assert {"id", "parent_node_id"} <= set(test_harness.TestGraphNodeDto.model_fields)
    assert {"task_id", "task_slug"} <= set(test_harness.TestEvaluationDto.model_fields)
    assert {
        "executions",
        "execution_count",
        "mutation_count",
        "resource_count",
        "thread_count",
        "context_event_count",
    } <= set(test_harness.TestRunStateDto.model_fields)


def test_read_endpoint_unmounted_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app_with_harness(monkeypatch, enabled=False)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404  # unmounted = route doesn't exist


def test_seed_requires_secret_header(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app_with_harness(monkeypatch, enabled=True, secret="ci-secret")
    client = TestClient(app)
    resp = client.post(
        "/api/test/write/run/seed",
        json={"experiment_definition_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 401


def test_seed_returns_500_when_secret_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app_with_harness(monkeypatch, enabled=True, secret=None)
    client = TestClient(app)
    resp = client.post(
        "/api/test/write/run/seed",
        json={"experiment_definition_id": "00000000-0000-0000-0000-000000000001"},
        headers={"X-Test-Secret": "anything"},
    )
    assert resp.status_code == 500


def test_reset_requires_secret_header(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app_with_harness(monkeypatch, enabled=True, secret="ci-secret")
    client = TestClient(app)
    resp = client.post("/api/test/write/reset", json={"cohort_prefix": "ci-smoke-"})
    assert resp.status_code == 401


def test_startup_plugin_loader_rejects_invalid_specs() -> None:
    with pytest.raises(RuntimeError, match="expected 'module:function'"):
        run_startup_plugins(("ergon_core.test_support.smoke_fixtures",))
