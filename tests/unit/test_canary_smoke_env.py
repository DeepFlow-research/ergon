"""Regression test: the real-LLM canary subprocess env must target the
host-side port that ``docker-compose.real-llm.yml`` actually publishes.

See ``docs/bugs/open/2026-04-21-inngest-port-mismatch.md``.
"""

import pytest

from tests.real_llm.benchmarks.test_smoke_stub import _subprocess_env


def test_subprocess_env_defaults_inngest_to_real_llm_host_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without an explicit override, INNGEST_API_BASE_URL must match the
    real-LLM overlay's host-published port (8288), not the Settings default
    or the CI overlay's mapping (8289)."""
    monkeypatch.delenv("INNGEST_API_BASE_URL", raising=False)

    env = _subprocess_env()

    assert env["INNGEST_API_BASE_URL"] == "http://127.0.0.1:8288"


def test_subprocess_env_respects_explicit_inngest_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator override (e.g. CI) wins over the default."""
    monkeypatch.setenv("INNGEST_API_BASE_URL", "http://localhost:8289")

    env = _subprocess_env()

    assert env["INNGEST_API_BASE_URL"] == "http://localhost:8289"


def test_subprocess_env_defaults_database_url_to_real_llm_host_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Postgres default mirrors ``docker-compose.real-llm.yml`` (5433:5432)."""
    monkeypatch.delenv("ERGON_DATABASE_URL", raising=False)

    env = _subprocess_env()

    assert env["ERGON_DATABASE_URL"] == "postgresql://ergon:ergon@127.0.0.1:5433/ergon"
