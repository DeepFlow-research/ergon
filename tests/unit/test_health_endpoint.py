"""`/health` returns 200 with `{"status": "ok"}` — liveness contract."""

import importlib

import pytest
from fastapi.testclient import TestClient


def _reload_app(monkeypatch: pytest.MonkeyPatch) -> "TestClient":
    # reason: importing fresh so test isolation doesn't depend on import order
    monkeypatch.delenv("ENABLE_TEST_HARNESS", raising=False)
    import ergon_core.core.api.app as app_mod

    importlib.reload(app_mod)
    return TestClient(app_mod.app)


def test_health_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _reload_app(monkeypatch)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
