"""Test-harness router: conditional mount, read DTO shape, write-gate secret."""

import os
from collections.abc import Iterator
from uuid import uuid4

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


def _build_app_with_harness(*, enabled: bool, secret: str | None = "ci-secret") -> FastAPI:
    app = FastAPI()
    prev_enable = os.environ.get("ENABLE_TEST_HARNESS")
    prev_secret = os.environ.get("TEST_HARNESS_SECRET")
    try:
        os.environ["ENABLE_TEST_HARNESS"] = "1" if enabled else "0"
        if secret is not None:
            os.environ["TEST_HARNESS_SECRET"] = secret
        else:
            os.environ.pop("TEST_HARNESS_SECRET", None)

        if enabled:
            # reason: import after env mutation so module-level gates see ENABLE_TEST_HARNESS=1
            from ergon_core.core.api.test_harness import get_session_dep, router

            app.include_router(router)
            app.dependency_overrides[get_session_dep] = _null_session_factory
    finally:
        if prev_enable is None:
            os.environ.pop("ENABLE_TEST_HARNESS", None)
        else:
            os.environ["ENABLE_TEST_HARNESS"] = prev_enable
        if prev_secret is None:
            os.environ.pop("TEST_HARNESS_SECRET", None)
        else:
            os.environ["TEST_HARNESS_SECRET"] = prev_secret
    return app


def test_read_endpoint_returns_404_for_unknown_run_id() -> None:
    app = _build_app_with_harness(enabled=True)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404


def test_read_endpoint_unmounted_when_disabled() -> None:
    app = _build_app_with_harness(enabled=False)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404  # unmounted = route doesn't exist
