"""Shared fixtures for E2E benchmark tests.

These tests run against a live docker-compose stack (postgres + inngest + api)
and require ARCANE_DATABASE_URL to point at the shared Postgres instance.
"""

import os
import subprocess

import pytest
from sqlalchemy import text
from sqlmodel import Session

from h_arcane.core.persistence.shared.db import get_engine


@pytest.fixture(scope="session", autouse=True)
def _require_database_url():
    url = os.environ.get("ARCANE_DATABASE_URL", "")
    if not url or url.startswith("sqlite"):
        pytest.skip(
            "E2E tests require ARCANE_DATABASE_URL pointing at a live Postgres. "
            "Run with docker-compose.ci.yml."
        )


@pytest.fixture(scope="session")
def db_session():
    """Provide a raw SQLModel session for assertion queries."""
    engine = get_engine()
    session = Session(engine)
    yield session
    session.close()


def run_benchmark(
    slug: str,
    *,
    worker: str,
    evaluator: str,
    limit: int = 1,
    cohort: str = "ci",
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run a benchmark via the arcane CLI and return the process result."""
    cmd = [
        "arcane", "benchmark", "run", slug,
        "--worker", worker,
        "--evaluator", evaluator,
        "--limit", str(limit),
        "--cohort", cohort,
        "--timeout", str(timeout),
    ]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout + 30)
